"""Destructive workflows run only against disposable synthetic workspaces/vaults."""
from dataclasses import replace
from io import BytesIO
import json
import base64
from pathlib import Path
from zipfile import ZipFile

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_removed_question_bulk import app, no_workers, login, SID, OWNER, VIEWER
from vop.actions import beep_wav
from vop.inputs.sources import capture_inline
from vop.reliable import configuration
from vop.service import create_app
from vop.workspace_backup import (ALL, DATA, connection, create_archive, inspect_archive,
    copy_database, selected_restore, apply_pending, queue_operation, mutable)


class Vault:
    """Fake OS encryption for offline tests only, never a production crypto scheme."""
    migrate_legacy = False
    def __init__(self, root): self.root = root; root.mkdir(exist_ok=True)
    def _crypt(self, data, decrypt=False):
        if decrypt:
            if not data.startswith(b'FAKE-OS:'): raise ValueError('Wrong account')
            return data[8:][::-1]
        return b'FAKE-OS:' + data[::-1]
    def _write_blob(self, path, data): path.write_bytes(data)
    def set(self, key, value): (self.root/(key+'.dpapi')).write_bytes(self._crypt(value.encode()))
    def get(self, key): return self._crypt((self.root/(key+'.dpapi')).read_bytes(),True).decode()
    def delete(self, key): (self.root/(key+'.dpapi')).unlink(missing_ok=True)


def seed(app):
    p, s, a = app.state.pipeline, app.state.store, app.state.actions
    s.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=0)
    p.run(SID, capture_inline(p.sources[SID]))
    a.save_action({'id':'bell','kind':'beep','name':'Bell','location':'browser','volume':50})
    a.save_automation({'id':'visitor','name':'Visitor','source_id':SID,'question_id':'red_square',
                       'trigger':'start','actions':['bell'],'enabled':True,'cooldown':60})
    a.save_action({'id':'clip','kind':'audio','name':'Clip','location':'browser','volume':50},audio=base64.b64encode(beep_wav()).decode())


def config(app): return configuration(app.state.pipeline.settings, app.state.store, app.state.reliable)['config']


def test_configuration_only_reset_restore_complete_workflow(app, tmp_path):
    seed(app)
    settings = app.state.pipeline.settings
    vault = Vault(tmp_path/'vault')
    vault.set('dashboard-access-key','keep-login')
    vault.set('unused-key','delete-this')
    app.state.secrets = vault
    callbacks=[]
    with TestClient(app) as client:
        csrf=login(client);app.state.shutdown_request=callbacks.append
        page=client.get('/release?tab=configuration')
        assert 'Factory reset' in page.text and 'Configuration' in page.text
        response=client.post('/release/backup',data={'csrf':csrf,'configs':'on'})
        assert response.status_code==200
        archive=response.content
        assert archive.startswith(b'PK'), response.text[:600]
        with ZipFile(BytesIO(archive)) as z:
            raw=z.read('workspace.sqlite3')
            assert b'\x89PNG\r\n\x1a\n' not in raw  # VACUUM removes freed captured pixels.
            assert json.loads(z.read('manifest.json'))['data'] is False
        assert client.post('/release/factory-reset/apply',data={'csrf':csrf,'confirmation':'no'}).status_code==400
        assert app.state.store.health()['observation_count'] > 0
        assert client.post('/release/factory-reset/apply',data={'csrf':csrf,'confirmation':'RESET'}).status_code==202
    assert callbacks==['restart']
    apply_pending(settings,vault)
    assert vault.get('dashboard-access-key')=='keep-login'
    assert not (vault.root/'unused-key.dpapi').exists()
    reset=create_app(settings,token=OWNER)
    assert not reset.state.pipeline.sources and not reset.state.actions.definitions()
    assert reset.state.pipeline.engine_unconfigured
    with reset.state.store.connection() as db:
        assert all(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0 for table in ALL if table!='release_settings')
        assert not db.execute("SELECT 1 FROM release_settings WHERE id LIKE 'saved_engine:%'").fetchone()
    reset.state.secrets=vault
    for worker in (reset.state.sampler, reset.state.reliable, reset.state.actions):
        worker.start=lambda:None
    with TestClient(reset) as client:
        csrf=login(client);reset.state.shutdown_request=callbacks.append
        response=client.post('/release/restore/preview?configs=on',content=archive,headers={'X-VOP-CSRF':csrf})
        assert response.status_code==200,response.text
        url=response.json()['url']
        assert client.get(url).status_code==200
        assert client.post(url+'/apply',data={'csrf':csrf}).status_code==202
    apply_pending(settings,vault)
    restored=create_app(settings,token=OWNER)
    assert SID in restored.state.pipeline.sources
    assert not restored.state.pipeline.engine_unconfigured
    assert restored.state.store.health()['observation_count']==0
    assert {r['id'] for r in restored.state.actions.definitions()}=={'bell','clip'}
    assert restored.state.actions.automations()[0]['id']=='visitor'
    assert restored.state.actions.paused()
    assert restored.state.reliable.paused()
    with restored.state.store.connection() as db:
        assert db.execute('SELECT length(payload) FROM action_audio WHERE id="clip"').fetchone()[0]>0
    assert not settings.database.with_name(settings.database.name+'.maintenance.json').exists()
    assert not list((settings.database.parent/'.vop-maintenance').iterdir())
    # Changes made after restore must win over the saved bootstrap on restart.
    q=restored.state.store.questions(SID)[0]['spec']
    edited=restored.state.store.edit_question(SID,replace(q,text='Edited after restore'),restored.state.store.policy(SID,q.question_id,q.version))
    restored.state.store.update_source(SID,enabled=False,retain_evidence=False,sample_interval_seconds=0)
    again=create_app(settings,token=OWNER)
    assert again.state.store.source_control(SID)['enabled'] is False
    assert again.state.store.questions(SID)[0]['spec'].text=='Edited after restore'


@pytest.mark.parametrize('configs,data',[(True,False),(False,True),(True,True)])
def test_archive_group_contents_and_restore_separation(app,tmp_path,configs,data):
    seed(app);vault=Vault(tmp_path/'vault')
    original=app.state.store.path
    archive=tmp_path/'backup.vop'
    create_archive(app.state.store,config(app),vault,archive,configs=configs,data=data)
    folder=tmp_path/'checked'
    manifest,_=inspect_archive(archive,folder,original,vault)
    with connection(folder/'workspace.sqlite3') as db:
        assert bool(db.execute('SELECT count(*) FROM observations').fetchone()[0]) is data
        assert bool(db.execute('SELECT count(*) FROM action_definitions').fetchone()[0]) is configs
    assert manifest['configuration'] is configs and manifest['data'] is data
    before_count=app.state.store.health()['observation_count']
    app.state.pipeline.run(SID,capture_inline(app.state.pipeline.sources[SID]))
    app.state.actions.save_action({'id':'new-action','kind':'beep','name':'New','location':'browser','volume':50})
    target=tmp_path/'selected.sqlite3'
    selected_restore(original,folder/'workspace.sqlite3',target,configs=configs,data=data)
    with connection(target) as db:
        # Unselected groups are preserved, not wiped.
        assert db.execute('SELECT count(*) FROM observations').fetchone()[0] == (before_count if data else before_count*2)
        assert db.execute('SELECT count(*) FROM action_definitions').fetchone()[0] == (2 if configs else 3)


def test_protected_settings_remain_encrypted_and_wrong_account_is_rejected(app,tmp_path):
    vault=Vault(tmp_path/'vault');vault.set('camera-key','private-camera-password')
    with app.state.store.connection() as db:
        db.execute('INSERT INTO release_settings VALUES(?,?)',('test-secret',json.dumps({'secret_ref':'camera-key'})))
    archive=tmp_path/'backup.vop'
    create_archive(app.state.store,config(app),vault,archive,configs=True,data=False)
    with ZipFile(archive) as z:
        assert b'private-camera-password' not in b''.join(z.read(name) for name in z.namelist())
        assert z.read('protected/camera-key.dpapi')==(vault.root/'camera-key.dpapi').read_bytes()
    class Wrong(Vault):
        def _crypt(self,*a,**kw): raise ValueError('Wrong account')
    with pytest.raises(ValueError,match='Wrong account'):
        inspect_archive(archive,tmp_path/'wrong',app.state.store.path,Wrong(tmp_path/'other'))
    inspect_archive(archive,tmp_path/'data-only',app.state.store.path,Wrong(tmp_path/'other'),decrypt_keys=False)


def test_corrupt_archive_and_schema_rejected_before_live_changes(app,tmp_path,monkeypatch):
    seed(app);vault=Vault(tmp_path/'vault');archive=tmp_path/'backup.vop'
    create_archive(app.state.store,config(app),vault,archive,configs=True,data=True)
    with ZipFile(archive) as z: members={name:z.read(name) for name in z.namelist()}
    members['workspace.sqlite3']+=b'corrupt'
    with ZipFile(tmp_path/'bad.vop','w') as z:
        for name,value in members.items():z.writestr(name,value)
    with pytest.raises(ValueError,match='checksum'):
        inspect_archive(tmp_path/'bad.vop',tmp_path/'bad',app.state.store.path,vault)
    assert app.state.store.health()['observation_count']>0
    monkeypatch.setattr('vop.workspace_backup.MAX_ARCHIVE',1)
    with pytest.raises(ValueError,match='2 GB'):
        create_archive(app.state.store,config(app),vault,tmp_path/'too-large.vop',configs=True,data=True)


def test_restore_upload_permissions_and_no_mutation_without_confirmation(app,tmp_path):
    seed(app);app.state.secrets=Vault(tmp_path/'vault')
    with TestClient(app) as client:
        csrf=login(client)
        for url in ('/release/factory-reset','/release/restore/not-real','/release/backup'):
            assert client.get(url,headers={'Authorization':'Bearer '+VIEWER}).status_code==403
        assert client.post('/release/restore/preview?configs=on',content=b'invalid').status_code==403
        assert client.post('/release/restore/preview?configs=on',content=b'invalid',headers={'X-VOP-CSRF':csrf}).status_code==400
        assert client.post('/release/factory-reset/apply',data={'csrf':csrf,'confirmation':'RESET'}).status_code==409
        assert app.state.store.health()['observation_count']>0


@pytest.mark.parametrize('failure',[OSError,KeyboardInterrupt])
def test_failed_or_interrupted_apply_recovers_database_and_protected_values(app,tmp_path,monkeypatch,failure):
    import vop.workspace_backup as backup
    seed(app);vault=Vault(tmp_path/'vault');vault.set('old-key','original');vault.set('dashboard-access-key','login')
    stage=tmp_path/'stage.sqlite3';copy_database(app.state.store.path,stage)
    with connection(stage) as db:
        with mutable(db): backup.remove_history(db)
    queue_operation(app.state.store,stage,config(app),{'new-key':vault._crypt(b'restored')},replace_configs=True)
    old_copy=backup.copy_database;failed=[False]
    def interrupt(source,destination):
        old_copy(source,destination)
        if Path(destination)==app.state.store.path and not failed[0]:
            failed[0]=True
            raise failure('Synthetic interruption after replacement')
    monkeypatch.setattr(backup,'copy_database',interrupt)
    with pytest.raises(failure): apply_pending(app.state.pipeline.settings,vault)
    if failure is OSError:
        assert app.state.store.health()['observation_count']>0
        assert vault.get('old-key')=='original'
        assert not (vault.root/'new-key.dpapi').exists()
    apply_pending(app.state.pipeline.settings,vault)
    assert app.state.store.health()['observation_count']==0
    assert vault.get('new-key')=='restored' and vault.get('dashboard-access-key')=='login'
    assert not (vault.root/'old-key.dpapi').exists()
    assert not list((app.state.store.path.parent/'.vop-maintenance').iterdir())


def test_notification_filters_hide_retired_and_deleted_unless_history_has_notifications(app):
    from vop.contracts import utcnow
    p,s,r=app.state.pipeline,app.state.store,app.state.reliable
    old=replace(p.sources[SID],source_id='old-camera',name='Tapo C200')
    s.configure(replace(p.settings,sources=(old,)));p.sources['old-camera']=old
    question=s.questions(SID)[0]['spec']
    deleted=replace(question,question_id='former-question',text='Former question')
    unused=replace(question,question_id='unused-question',text='Never used question')
    s.edit_question(SID,deleted,s.policy(SID,question.question_id,question.version))
    s.edit_question(SID,unused,s.policy(SID,question.question_id,question.version))
    for rid,sid,qid in (('current-rule',SID,'red_square'),('old-rule','old-camera','red_square'),('former-rule',SID,'former-question')):
        r.save_rule({'id':rid,'source_id':sid,'question_id':qid,'kind':'count','threshold':0})
        with s.connection() as db:
            db.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(rid,rid,1,utcnow().isoformat(),'count','warning',sid,qid,'1',None,'open','',json.dumps({'synthetic':True})))
    with s.connection() as db:
        for key in ('removed_source:old-camera','removed_question:'+SID+':former-question','removed_question:'+SID+':unused-question'):
            db.execute('INSERT INTO release_settings VALUES(?,?)',(key,'true'))
    p.sources.pop('old-camera')
    with TestClient(app) as client:
        login(client)
        default=BeautifulSoup(client.get('/release?tab=notifications').text,'html.parser')
        assert 'Tapo C200' not in default.get_text() and 'Former question' not in default.get_text()
        assert 'current-rule' in default.get_text() and 'former-rule' not in default.get_text()
        history=BeautifulSoup(client.get('/release?tab=notifications&include_history=on').text,'html.parser')
        assert history.select_one('option[value="old-camera"]').text=='Tapo C200 (Retired)'
        assert history.select_one('option[value="former-question"]').text=='Former question (Historical)'
        assert not history.select_one('option[value="unused-question"]')
        assert 'former-rule' in history.get_text()


def test_schema_changes_and_archive_paths_are_rejected(app,tmp_path):
    import hashlib
    vault=Vault(tmp_path/'vault');archive=tmp_path/'backup.vop'
    create_archive(app.state.store,config(app),vault,archive,configs=True,data=True)
    with ZipFile(archive) as z: members={name:z.read(name) for name in z.namelist()}
    dbpath=tmp_path/'changed.sqlite3';dbpath.write_bytes(members['workspace.sqlite3'])
    with connection(dbpath) as db: db.execute('CREATE TABLE surprise(value)')
    members['workspace.sqlite3']=dbpath.read_bytes()
    manifest=json.loads(members['manifest.json'])
    manifest['files']['workspace.sqlite3']=hashlib.sha256(members['workspace.sqlite3']).hexdigest()
    members['manifest.json']=json.dumps(manifest).encode()
    changed=tmp_path/'changed.vop'
    with ZipFile(changed,'w') as z:
        for name,value in members.items():z.writestr(name,value)
    with pytest.raises(ValueError,match='structure'):
        inspect_archive(changed,tmp_path/'schema-rejected',app.state.store.path,vault)
    members['../escape']=b'not allowed'
    manifest['files']['../escape']=hashlib.sha256(b'not allowed').hexdigest()
    members['manifest.json']=json.dumps(manifest).encode()
    with ZipFile(tmp_path/'paths.vop','w') as z:
        for name,value in members.items():z.writestr(name,value)
    with pytest.raises(ValueError,match='Unexpected'):
        inspect_archive(tmp_path/'paths.vop',tmp_path/'paths-rejected',app.state.store.path,vault)
    assert not (tmp_path/'escape').exists()


def test_preview_cancel_cleans_files_and_unavailable_group_is_kept(app,tmp_path):
    seed(app);app.state.secrets=Vault(tmp_path/'vault')
    with TestClient(app) as client:
        csrf=login(client)
        archive=client.post('/release/backup',data={'csrf':csrf,'configs':'on'}).content
        response=client.post('/release/restore/preview?configs=on&data=on',content=archive,headers={'X-VOP-CSRF':csrf})
        assert response.status_code==200
        url=response.json()['url']
        page=client.get(url)
        assert 'Replace: Configuration' in page.text and 'not included in the backup is kept' in page.text
        assert client.post(url+'/cancel',data={'csrf':csrf}).status_code==200
        assert client.get(url).status_code==400
        assert app.state.store.health()['observation_count']>0


def test_notification_resume_requires_operator_and_does_not_replay_on_restore(app):
    with app.state.store.connection() as db:
        db.execute("INSERT INTO release_settings VALUES('notification_rules_paused','true')")
    called=[]
    app.state.reliable.evaluate=lambda *a:called.append('evaluate')
    app.state.reliable.retry=lambda *a:called.append('send')
    app.state.reliable.tick()
    assert not called
    with TestClient(app) as client:
        csrf=login(client)
        assert 'Resume notification rules' in client.get('/release?tab=rules').text
        assert client.post('/release/rules/resume',headers={'Authorization':'Bearer '+VIEWER}).status_code==403
        assert client.post('/release/rules/resume',data={'csrf':csrf}).status_code==200
    app.state.reliable.tick()
    assert called==['evaluate','send']


def test_camera_profiles_masks_names_and_keys_restore_after_reset(app,tmp_path):
    from vop.integration_ui import camera_source
    vault=Vault(tmp_path/'vault');settings=app.state.pipeline.settings
    record={'source_id':'test-camera','model':'C200','endpoint_ref':'test-endpoint','credentials_ref':'test-camera-key',
            'allowed_hosts':['192.168.1.100'],'persistent_capture':False,'privacy_masks':[[0,0,.2,.2]]}
    camera=replace(camera_source(record),name='Test porch')
    app.state.store.configure(replace(settings,sources=(camera,)))
    app.state.pipeline.sources[camera.source_id]=camera
    with app.state.store.connection() as db:
        for key,value in (('camera_profile:test-camera',record),('camera_name:test-camera','Test porch')):
            db.execute('INSERT INTO release_settings VALUES(?,?)',(key,json.dumps(value)))
    vault.set('test-endpoint','rtsp://192.168.1.100:554/stream1')
    vault.set('test-camera-key',json.dumps({'username':'synthetic-user','password':'synthetic-password'}))
    snapshot=config(app);archive=tmp_path/'camera.vop'
    create_archive(app.state.store,snapshot,vault,archive,configs=True,data=False)
    clean=tmp_path/'empty.sqlite3';copy_database(app.state.store.path,clean)
    with connection(clean) as db:
        with mutable(db):
            for table in ALL:db.execute(f'DELETE FROM {table}')
    empty=dict(snapshot,sources=[])
    queue_operation(app.state.store,clean,empty,{},reset=True)
    apply_pending(settings,vault)
    assert not (vault.root/'test-camera-key.dpapi').exists()
    inspect_archive(archive,tmp_path/'checked',app.state.store.path,vault)
    selected_restore(app.state.store.path,tmp_path/'checked/workspace.sqlite3',tmp_path/'restored.sqlite3',configs=True,data=False)
    protected={p.stem:p.read_bytes() for p in (tmp_path/'checked/protected').glob('*.dpapi')}
    queue_operation(app.state.store,tmp_path/'restored.sqlite3',snapshot,protected,replace_configs=True)
    apply_pending(settings,vault)
    restored=create_app(settings,token=OWNER)
    camera=restored.state.pipeline.sources['test-camera']
    assert camera.name=='Test porch' and camera.settings['persistent_capture'] is False
    assert camera.settings['privacy_masks']==[[0,0,.2,.2]]
    assert json.loads(vault.get('test-camera-key'))['password']=='synthetic-password'
    assert vault.get('test-endpoint')=='rtsp://192.168.1.100:554/stream1'


def test_maintenance_waits_for_inflight_writes_and_blocks_new_writes(app,tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from starlette.responses import JSONResponse
    entered,release=Event(),Event()
    app.state.secrets=Vault(tmp_path/'vault')
    @app.route('/actions/test-inflight-write',methods=['POST'])
    def slow():
        entered.set()
        assert release.wait(20)
        return JSONResponse({'done':True})
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=2) as workers:
        csrf=login(client);app.state.shutdown_request=lambda mode:None
        old=workers.submit(client.post,'/actions/test-inflight-write',data={'csrf':csrf})
        assert entered.wait(10)
        pending=workers.submit(client.post,'/release/factory-reset/apply',data={'csrf':csrf,'confirmation':'RESET'})
        try:
            from time import monotonic,sleep
            until=monotonic()+10
            while not app.state.pipeline.workspace_maintenance and monotonic()<until:sleep(.01)
            assert app.state.pipeline.workspace_maintenance and not pending.done()
            assert client.post('/actions/test-inflight-write',data={'csrf':csrf}).status_code==503
        finally:
            release.set()
        assert old.result(timeout=30).status_code==200
        assert pending.result(timeout=30).status_code==202


def test_upload_and_restart_browser_contract():
    import shutil,subprocess
    from vop.workspace_ui import SCRIPT
    node=shutil.which('node')
    if not node: pytest.skip('Node is needed for the browser contract')
    harness=r'''
const assert=require('node:assert/strict');let handler,assigned,replaced,mode='upload',calls=[];
global.document={addEventListener:(_,fn)=>handler=fn};
global.location={assign:url=>assigned=url,replace:url=>replaced=url};
const storage=new Map([['vop-old','old'],['unrelated','keep']]);
global.sessionStorage={get length(){return storage.size;},key:i=>[...storage.keys()][i],removeItem:k=>storage.delete(k)};
global.setTimeout=fn=>{queueMicrotask(fn);return 0;};
global.FormData=class{*[Symbol.iterator](){yield ['csrf','test-csrf'];yield ['confirmation','RESET'];}};
const file={synthetic:true},button={disabled:false},status={hidden:true,textContent:''};
const form={action:'/release/restore/preview',elements:{backup:{files:[file]},csrf:{value:'test-csrf'},configs:{checked:true},data:{checked:false}},
 matches:()=>true,hasAttribute:()=>mode==='upload',querySelector:s=>s==='button'?button:status};
global.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>mode==='upload'?{url:'/release/restore/preview-token'}:
 url==='/api/v1/health'?{instance_id:'new'}:{instance_id:'old',factory_reset:true,complete_message:'Restored safely'}};};
new Function(SOURCE)();
(async()=>{
 await handler({target:form,preventDefault(){}});
 assert.equal(assigned,'/release/restore/preview-token');
 assert.equal(calls[0].url,'/release/restore/preview?configs=on');
 assert.equal(calls[0].options.headers['X-VOP-CSRF'],'test-csrf');
 assert.equal(calls[0].options.body,file);
 mode='apply';calls=[];form.action='/release/factory-reset/apply';
 await handler({target:form,preventDefault(){}});
 assert.equal(calls[0].options.body.get('confirmation'),'RESET');
 assert.ok(replaced.includes('Restored%20safely'));
 assert.ok(!storage.has('vop-old'));assert.equal(storage.get('unrelated'),'keep');
 console.log('PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('SOURCE',json.dumps(SCRIPT))
    result=subprocess.run([node],input=harness,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='PASS'
