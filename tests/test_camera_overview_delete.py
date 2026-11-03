"""Camera listing and permanent deletion with synthetic frames/credentials only."""
from dataclasses import replace
import json

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_removed_question_bulk import app,no_workers,login,SID,OWNER,VIEWER
from vop.config import SourceSpec
from vop.inputs.sources import capture_inline
from vop.contracts import ProviderError, utcnow
from vop.service import create_app
from vop.deletion_audit import audit


def camera(app,sid,endpoint,interval=10):
    p,s=app.state.pipeline,app.state.store
    source=SourceSpec(sid,'Test '+sid,'rtsp',{'endpoint_secret_ref':endpoint,'secret_ref':'shared-account','allowed_hosts':['192.168.1.100'],
                     'privacy_masks':[[0,0,.2,1]]},p.sources[SID].questions)
    s.configure(replace(p.settings,sources=(source,)));p.sources[sid]=source
    s.update_source(sid,enabled=True,retain_evidence=True,sample_interval_seconds=interval)
    record={'source_id':sid,'model':'C200','endpoint_ref':endpoint,'credentials_ref':'shared-account','allowed_hosts':['192.168.1.100'],'privacy_masks':[[0,0,.2,1]]}
    with s.connection() as db:db.execute('INSERT INTO release_settings VALUES(?,?)',('camera_profile:'+sid,json.dumps(record)))
    app.state.secrets.set(endpoint,'rtsp://192.168.1.100:554/stream1')
    app.state.secrets.set('shared-account',json.dumps({'username':'synthetic','password':'synthetic'}))
    return source


def test_overview_columns_rates_and_flags_are_passive(app,monkeypatch):
    first=camera(app,'first','first-endpoint')
    second=camera(app,'paused','paused-endpoint',0)
    app.state.pipeline.sources['paused']=replace(second,settings={**second.settings,'persistent_capture':False,'privacy_masks':[]})
    def forbidden(*a,**kw):pytest.fail('Overview must not decrypt credentials, capture or open streams')
    monkeypatch.setattr(app.state.secrets,'get',forbidden)
    monkeypatch.setattr(app.state.pipeline.capture_adapter,'capture',forbidden)
    monkeypatch.setattr(app.state.pipeline.persistent_cameras,'factory',forbidden)
    with TestClient(app) as client:
        login(client)
        doc=BeautifulSoup(client.get('/cameras').text,'html.parser')
        headers=[t.text for t in doc.select('thead th')]
        assert {'Target samples/hour','Keep connection open','Save images','Privacy mask','Last observation image'} <= set(headers)
        row=doc.find('a',string=first.name).find_parent('tr')
        cells=[c.get_text(' ',strip=True) for c in row.find_all('td')]
        assert cells[2:6]==['Monitoring','00:00:10.0','360.0','3 / 3']
        assert cells[6:10]==['On','Yes','Yes (1)','Not yet']
        row=doc.find('a',string=second.name).find_parent('tr')
        cells=[c.get_text(' ',strip=True) for c in row.find_all('td')]
        assert cells[2]=='Paused' and cells[4]=='0.0' and cells[6]=='Off' and cells[8]=='No'
        app.state.store.update_source('first',enabled=False,retain_evidence=True,sample_interval_seconds=10)
        doc=BeautifulSoup(client.get('/cameras').text,'html.parser')
        cells=doc.find('a',string=first.name).find_parent('tr').find_all('td')
        assert cells[2].text=='Disabled' and cells[4].text=='0.0'
        usb=SourceSpec('usb','Desk USB','usb',{'device':0},first.questions,sample_interval_seconds=5)
        app.state.store.configure(replace(app.state.pipeline.settings,sources=(usb,)))
        app.state.pipeline.sources['usb']=usb
        doc=BeautifulSoup(client.get('/cameras').text,'html.parser')
        cells=doc.find('a',string='Desk USB').find_parent('tr').find_all('td')
        assert cells[4].text=='720.0' and cells[6].text=='Not applicable'


def test_retired_camera_purge_removes_data_links_keys_and_does_not_resurrect(app):
    p,s,a=app.state.pipeline,app.state.store,app.state.actions
    first=camera(app,'retire-this','delete-endpoint')
    other=camera(app,'keep-this','keep-endpoint')
    # A camera supplied by launcher configuration need not have a GUI profile row.
    # Its runtime adapter settings must still protect shared credentials.
    with s.connection() as db:db.execute("DELETE FROM release_settings WHERE id='camera_profile:keep-this'")
    for source in (first,other):
        frame=replace(capture_inline(p.sources[SID]),source_id=source.source_id)
        p.run(source.source_id,frame)
    a.save_action({'id':'bell','name':'Reusable bell','kind':'beep','location':'browser','volume':50})
    a.save_automation({'id':'watch-camera','name':'Watch','source_id':first.source_id,'question_id':'red_square','trigger':'start','actions':['bell'],'enabled':True,'cooldown':60})
    app.state.reliable.save_rule({'id':'camera-rule','source_id':first.source_id,'question_id':'red_square','kind':'count','threshold':1})
    for source in (first,other):
        app.state.reliable.save_rule({'id':'moved-rule','source_id':source.source_id,'question_id':'red_square','kind':'count','threshold':1})
    with s.connection() as db:
        for revision in (1,2):db.execute('INSERT INTO rule_states VALUES(?,?,?)',(f'moved-rule:{revision}:1:health',0,1))
        now=utcnow().isoformat()
        db.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',('camera-alert','camera-rule',1,now,'count','warning',first.source_id,'red_square','1',None,'open','',json.dumps({'synthetic':True})))
        db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?)',('camera-alert','dashboard','delivered',1,now))
        for job,source,mid in (('camera-job',first,'watch-camera'),('keep-job',other,None)):
            db.execute('INSERT INTO action_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(job,mid,'bell',now,now,now,'completed',1,json.dumps(a.definitions()[0]),json.dumps({'source_id':source.source_id,'question_id':'red_square'}),'',None))
    with TestClient(app) as client:
        csrf=login(client)
        assert client.get('/ui/sources/retire-this/delete').status_code==400
        assert client.post('/ui/sources/retire-this/remove',data={'csrf':csrf}).status_code==200
        doc=BeautifulSoup(client.get('/cameras').text,'html.parser')
        assert doc.select_one('a[href="/ui/sources/retire-this/delete"]')
        assert client.get('/ui/sources/retire-this/delete',headers={'Authorization':'Bearer '+VIEWER}).status_code==403
        preview=client.get('/ui/sources/retire-this/delete')
        assert preview.status_code==200 and 'Saved images: 1' in preview.text
        assert 'Action activity: 1' in preview.text and 'Notifications: 1' in preview.text
        assert client.post('/ui/sources/retire-this/delete',data={'csrf':csrf,'confirmation':'no'}).status_code==400
        response=client.post('/ui/sources/retire-this/delete',data={'csrf':csrf,'confirmation':'DELETE'})
        assert response.status_code==200
        assert 'retire-this' not in p.sources and 'retire-this' not in p.removed_sources
        assert client.post('/ui/sources/retire-this/restore',data={'csrf':csrf}).status_code==400
    with s.connection() as db:
        for table in ('sources','query_controls','query_policies','question_versions','observations','runs','frames','events','alerts'):
            column='id' if table=='sources' else 'source_id'
            assert db.execute(f'SELECT count(*) FROM {table} WHERE {column}=?',('retire-this',)).fetchone()[0]==0
        assert not db.execute("SELECT 1 FROM release_settings WHERE id LIKE 'camera_%:retire-this'").fetchone()
        assert not db.execute('SELECT 1 FROM automations WHERE id="watch-camera"').fetchone()
        assert not db.execute('SELECT 1 FROM rules WHERE id="camera-rule"').fetchone()
        assert db.execute('SELECT 1 FROM rules WHERE id="moved-rule"').fetchone()
        assert not db.execute('SELECT 1 FROM rule_states WHERE id="moved-rule:1:1:health"').fetchone()
        assert db.execute('SELECT 1 FROM rule_states WHERE id="moved-rule:2:1:health"').fetchone()
        assert not db.execute('SELECT 1 FROM deliveries WHERE alert_id="camera-alert"').fetchone()
        assert not db.execute('SELECT 1 FROM action_jobs WHERE id="camera-job"').fetchone()
        assert db.execute('SELECT 1 FROM action_jobs WHERE id="keep-job"').fetchone()
        assert db.execute('SELECT count(*) FROM frames WHERE source_id="keep-this"').fetchone()[0]==1
        assert audit(db)['result']=='PASS'
    assert a.definitions()[0]['id']=='bell'
    assert json.loads(app.state.secrets.get('shared-account'))['username']=='synthetic'
    assert app.state.secrets.get('keep-endpoint')
    with pytest.raises(ProviderError):app.state.secrets.get('delete-endpoint')
    restarted=create_app(replace(p.settings,sources=(*p.settings.sources,first,other)),token=OWNER)
    assert 'retire-this' not in restarted.state.pipeline.sources and 'retire-this' not in restarted.state.pipeline.removed_sources
    assert 'keep-this' in restarted.state.pipeline.sources


def test_new_camera_skips_permanently_reserved_id(app):
    from test_unified_camera_settings import body
    with app.state.store.connection() as db:
        db.execute("INSERT INTO release_settings VALUES('removed_source:tapo-c200','true')")
        db.execute("INSERT INTO release_settings VALUES('deleted_source:tapo-c200','true')")
    with TestClient(app) as client:
        csrf=login(client)
        assert client.post('/cameras/save',data=body(csrf,source_id='')).status_code==200
        assert 'tapo-c200-2' in app.state.pipeline.sources and 'tapo-c200' not in app.state.pipeline.sources
        failed=client.post('/cameras/save',data=body(csrf),headers={'Accept':'text/html'})
        assert failed.status_code==400 and 'permanently deleted' in failed.text
