"""One camera form saves connection and observation settings without live capture."""
from dataclasses import replace

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_removed_question_bulk import app, no_workers, login
from vop.config import SourceSpec
from vop.inputs.sources import SourceAdapters
from vop.service import create_app
from test_phase4_worker import OWNER
import json


def body(csrf, **changes):
    return {'csrf':csrf,'source_id':'tapo-c200','model':'C200','name':'Front door',
            'endpoint':'rtsp://192.168.1.100:554/stream1','username':'offline-user','password':'offline-password',
            'observation_settings':'1','enabled':'on','sample_interval_seconds':'00:00:12.0','retain_evidence':'on', **changes}


def test_one_form_all_settings_persist_and_old_editor_redirects(app, monkeypatch):
    monkeypatch.setattr(SourceAdapters,'capture',lambda *_:pytest.fail('Saving must not open a camera'))
    with TestClient(app) as client:
        csrf=login(client)
        assert client.post('/cameras/save',data=body(csrf)).status_code==200
        page=client.get('/cameras/tapo-c200/edit')
        soup=BeautifulSoup(page.text,'html.parser')
        form=soup.select_one('form.camera-editor')
        assert [h.text for h in form.select('section > h2')]==['Camera','Connection','Observations','Recorded images','Privacy mask']
        assert form['action']=='/cameras/save'
        assert form.select_one('[name=password]').get('value','')==''
        assert all(form.select_one('[name='+name+']') for name in ('endpoint','username','enabled','sample_interval_seconds','retain_evidence'))
        assert form.select_one('[name=sample_interval_seconds]')['value']=='00:00:12.0'
        old=client.get('/ui/sources/tapo-c200')
        assert old.url.path=='/cameras/tapo-c200'
        assert client.get('/cameras/tapo-c200/rename').url.path=='/cameras/tapo-c200'
        changed=body(csrf,password='',username='updated-user',name='Driveway',sample_interval_seconds='00:00:25.0')
        assert client.post('/cameras/save',data=changed).status_code==200
        assert app.state.secrets.camera('tapo-c200-credentials')=={'username':'updated-user','password':'offline-password'}
        assert app.state.store.source_control('tapo-c200')=={'enabled':True,'retain_evidence':True,'sample_interval_seconds':25}
        # Legacy connection-only clients preserve observation settings.
        legacy={k:v for k,v in changed.items() if k not in ('observation_settings','enabled','retain_evidence','sample_interval_seconds')}
        assert client.post('/cameras/save',data=legacy).status_code==200
        assert app.state.store.source_control('tapo-c200')['sample_interval_seconds']==25
    restarted=create_app(app.state.pipeline.settings,token=OWNER)
    assert restarted.state.pipeline.sources['tapo-c200'].name=='Driveway'
    assert restarted.state.store.source_control('tapo-c200')==app.state.store.source_control('tapo-c200')


def test_camera_privacy_editor_saves_and_clears_for_rtsp_and_usb(app,monkeypatch):
    monkeypatch.setattr(SourceAdapters,'capture',lambda *_:pytest.fail('Saving privacy must not capture'))
    with TestClient(app) as client:
        csrf=login(client)
        assert client.post('/cameras/save',data=body(csrf,privacy_masks='[[0,0,0.25,1]]')).status_code==200
        source=app.state.pipeline.sources['tapo-c200']
        assert source.settings['privacy_masks']==((0.,0.,.25,1.),)
        html=BeautifulSoup(client.get('/cameras/tapo-c200').text,'html.parser')
        assert json.loads(html.select_one('[name=privacy_masks]')['value'])==[[0,0,.25,1]]
        # Existing connection-only clients must not silently discard saved privacy.
        assert client.post('/cameras/save',data=body(csrf,password='')).status_code==200
        restarted=create_app(app.state.pipeline.settings,token=OWNER)
        assert restarted.state.pipeline.sources['tapo-c200'].settings['privacy_masks']==[[0,0,.25,1]]
        before=app.state.secrets.get('tapo-c200-endpoint')
        assert client.post('/cameras/save',data=body(csrf,privacy_masks='[[0,0,2,1]]')).status_code==400
        assert app.state.secrets.get('tapo-c200-endpoint')==before
        assert client.post('/cameras/save',data=body(csrf,password='',privacy_masks='[]')).status_code==200
        assert not app.state.pipeline.sources['tapo-c200'].settings['privacy_masks']
        usb=SourceSpec('usb-fixture','Desk camera','usb',{'device':0},source.questions)
        app.state.store.configure(replace(app.state.pipeline.settings,sources=(usb,)))
        app.state.pipeline.sources[usb.source_id]=usb
        response=client.post('/cameras/save',data={'csrf':csrf,'source_id':usb.source_id,'name':usb.name,'privacy_masks':'[[0,0,0.5,1]]'})
        assert response.status_code==200
    settings=replace(app.state.pipeline.settings,sources=(usb,))
    restarted=create_app(settings,token=OWNER)
    assert restarted.state.pipeline.sources[usb.source_id].settings['privacy_masks']==[[0,0,.5,1]]


def test_invalid_interval_changes_nothing_and_pause_keeps_connection(app):
    with TestClient(app) as client:
        csrf=login(client)
        client.post('/cameras/save',data=body(csrf))
        before=app.state.store.source_control('tapo-c200')
        saved=app.state.secrets.get('tapo-c200-endpoint')
        for invalid in ('00:00:00.5','01:00:01.0','bad'):
            assert client.post('/cameras/save',data=body(csrf,endpoint='rtsp://192.168.1.101:554/stream1',sample_interval_seconds=invalid)).status_code==400
            assert app.state.secrets.get('tapo-c200-endpoint')==saved
            assert app.state.store.source_control('tapo-c200')==before
        paused=body(csrf,password='',sample_interval_seconds='00:00:00.0')
        paused.pop('retain_evidence'); paused.pop('enabled')
        assert client.post('/cameras/save',data=paused).status_code==200
        assert app.state.store.source_control('tapo-c200')=={'enabled':False,'retain_evidence':False,'sample_interval_seconds':0}
        assert app.state.secrets.get('tapo-c200-endpoint')==saved


def test_usb_uses_same_editor_and_preserves_device(app):
    source=SourceSpec('usb-fixture','Desk camera','usb',{'device':0},())
    store,pipeline=app.state.store,app.state.pipeline
    store.configure(replace(pipeline.settings,sources=(source,)))
    pipeline.sources[source.source_id]=source
    with TestClient(app) as client:
        csrf=login(client)
        page=BeautifulSoup(client.get('/cameras/usb-fixture/edit').text,'html.parser')
        assert page.select_one('form.camera-editor')
        assert not page.select('[name=endpoint], [name=password]')
        response=client.post('/cameras/save',data={'csrf':csrf,'source_id':source.source_id,'name':'Office',
              'observation_settings':'1','enabled':'on','retain_evidence':'on','sample_interval_seconds':'00:00:20.0'})
        assert response.status_code==200
        assert pipeline.sources[source.source_id].settings['device']==0
        assert pipeline.sources[source.source_id].name=='Office'
        assert store.source_control(source.source_id)=={'enabled':True,'retain_evidence':True,'sample_interval_seconds':20}


def test_single_camera_entry_opens_complete_page_and_legacy_edit_redirects(app, monkeypatch):
    monkeypatch.setattr(SourceAdapters, 'capture', lambda *_:pytest.fail('Opening a camera page must not capture'))
    with TestClient(app) as client:
        csrf=login(client)
        client.post('/cameras/save',data=body(csrf))
        listing=BeautifulSoup(client.get('/cameras').text,'html.parser')
        buttons=listing.select('.camera-list .actions a')
        assert [(b.text,b['href']) for b in buttons]==[('Manage camera','/cameras/tapo-c200')]
        page=client.get(buttons[0]['href'])
        soup=BeautifulSoup(page.text,'html.parser')
        assert soup.select_one('h1').text=='Front door'
        form=soup.select_one('form.camera-editor')
        assert form and not form.select('form')
        assert form.select_one('[name=endpoint]') and form.select_one('[name=sample_interval_seconds]')
        assert soup.select_one('a[href="/?view=questions&source=tapo-c200"]')
        assert soup.select_one('a[href="/ui/sources/tapo-c200/remove"]')
        assert form.select_one('button[name=connect]')['value']=='1'
        assert form.select_one('button:not([type]),button[type=submit]').text=='Save settings'  # Enter must not trigger a connection test.
        assert 'Open camera' not in page.text and 'Edit settings' not in page.text
        assert client.get('/cameras/tapo-c200/edit').url.path=='/cameras/tapo-c200'


def test_save_and_test_uses_the_new_form_values_without_inference(app, monkeypatch):
    from vop.inputs.sources import capture_inline
    captured=[]
    def capture(_, source):
        captured.append(app.state.secrets.get(source.settings['endpoint_secret_ref']))
        return replace(capture_inline(app.state.pipeline.sources['synthetic-scene']), source_id=source.source_id)
    monkeypatch.setattr(SourceAdapters, 'capture', capture)
    with TestClient(app) as client:
        csrf=login(client)
        client.post('/cameras/save',data=body(csrf))
        before=app.state.store.health()['observation_count']
        response=client.post('/cameras/save',data=body(csrf,password='',endpoint='rtsp://192.168.1.101:554/stream1',connect='1'))
        assert response.status_code==200 and 'Capture succeeded' in response.text
        assert captured==['rtsp://192.168.1.101:554/stream1']
        assert app.state.store.health()['observation_count']==before
        assert app.state.store.source_control('tapo-c200')['sample_interval_seconds']==12
        assert '/cameras/tapo-c200' in response.text
