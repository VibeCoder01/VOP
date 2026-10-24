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
        assert [h.text for h in form.select('section > h2')]==['Camera','Connection','Observations','Recorded images']
        assert form['action']=='/cameras/save'
        assert form.select_one('[name=password]').get('value','')==''
        assert all(form.select_one('[name='+name+']') for name in ('endpoint','username','enabled','sample_interval_seconds','retain_evidence'))
        assert form.select_one('[name=sample_interval_seconds]')['value']=='00:00:12.0'
        old=client.get('/ui/sources/tapo-c200')
        assert old.url.path=='/cameras/tapo-c200/edit'
        assert client.get('/cameras/tapo-c200/rename').url.path=='/cameras/tapo-c200/edit'
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
