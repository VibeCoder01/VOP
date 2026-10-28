"""Offline diagnostics and trusted-name recovery; no cameras, SSH or real engine."""
from datetime import timedelta
from types import SimpleNamespace
import socket

import pytest
from starlette.testclient import TestClient

from test_phase3_release import app, HEADERS, VIEWER, TOKEN, SID
from vop.contracts import ProviderError, utcnow
from vop.diagnostics import snapshot
from vop.worker_session import antec_target, WorkerSession


def test_primary_and_short_names_share_original_trust_identity(monkeypatch):
    calls = []
    def resolve(host, *args, **kw):
        calls.append(host)
        if host == 'antec.local': raise socket.gaierror()
        return [('synthetic',)]
    monkeypatch.setattr('vop.worker_session.socket.getaddrinfo', resolve)
    assert antec_target() == ('antec', ['-o','HostKeyAlias=antec.local'])
    assert calls == ['antec.local','antec']
    monkeypatch.setattr('vop.worker_session.socket.getaddrinfo', lambda *a,**kw: [('synthetic',)])
    assert antec_target() == ('antec.local', [])
    def unavailable(*a,**kw): raise socket.gaierror()
    monkeypatch.setattr('vop.worker_session.socket.getaddrinfo', unavailable)
    with pytest.raises(ProviderError, match='antec_name_unresolved'): antec_target()


def test_fallback_is_used_by_session_without_changing_key_check(monkeypatch):
    import io
    import subprocess
    import shutil
    commands=[]
    monkeypatch.setattr('vop.worker_session.antec_target', lambda: ('antec',['-o','HostKeyAlias=antec.local']))
    monkeypatch.setattr(shutil,'which', lambda name:'trusted-ssh')
    class Listener:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def bind(self,where):pass
    monkeypatch.setattr(socket,'socket',Listener)
    monkeypatch.setattr(subprocess,'Popen',lambda command,**kw: (commands.append(command),SimpleNamespace(poll=lambda:None,stdin=io.BytesIO()))[1])
    session=WorkerSession();session.start(15)
    assert commands[0][-2] == 'antec'
    assert 'StrictHostKeyChecking=yes' in commands[0] and 'HostKeyAlias=antec.local' in commands[0]
    assert session.connection_host == 'antec'


def test_page_and_snapshot_are_passive_redacted_and_view_accessible(app,monkeypatch):
    def forbidden(*a,**kw):pytest.fail('Passive diagnostics must not connect to a camera, SSH or an engine')
    monkeypatch.setattr(app.state.pipeline.capture_adapter,'capture',forbidden)
    monkeypatch.setattr('vop.worker_session.socket.getaddrinfo',forbidden)
    app.state.pipeline.auto_worker=SimpleNamespace(last_failure=ProviderError('worker_reconnect_failed','must-not-display-secret'),ensure_ready=forbidden)
    app.state.sampler.last_error='worker_reconnect_failed'
    client=TestClient(app)
    response=client.get('/diagnostics',headers=HEADERS)
    assert response.status_code==200 and 'Diagnostics' in response.text
    assert 'Check and reconnect engine' in response.text
    assert 'must-not-display-secret' not in response.text
    data=client.get('/api/v1/diagnostics',headers=HEADERS).json()
    assert data['engine']['error']=='worker_reconnect_failed' and data['cameras'][0]['interval']==0
    assert not data['scheduler_running']
    assert client.get('/diagnostics',headers={'Authorization':'Bearer '+VIEWER}).status_code==200
    assert 'Check and reconnect engine' not in client.get('/diagnostics',headers={'Authorization':'Bearer '+VIEWER}).text
    assert client.post('/diagnostics/reconnect',headers={'Authorization':'Bearer '+VIEWER}).status_code==403
    from test_phase2_browser_storage import login
    login(client,TOKEN)
    assert client.get('/diagnostics').status_code==200
    assert client.post('/diagnostics/reconnect',data={}).status_code==403


def test_worker_failure_does_not_claim_camera_disconnected_and_backoff_is_visible(app):
    pipeline=app.state.pipeline
    with app.state.store.connection() as db:
        db.execute('UPDATE source_controls SET sample_interval_seconds=10 WHERE source_id=?',(SID,))
    def unavailable():raise ProviderError('antec_name_unresolved','Private error details')
    pipeline.auto_worker=SimpleNamespace(ensure_ready=unavailable,last_failure=ProviderError('antec_name_unresolved','Private'))
    app.state.sampler.tick(now=100)
    assert not pipeline.busy.locked() and pipeline.activity is None
    row=app.state.store.sources((SID,))[0]
    assert row['status']=='WAITING_FOR_ENGINE'
    assert app.state.sampler.failures[SID]==1 and app.state.sampler.deadlines[SID]==120
    assert app.state.sampler.source_errors[SID]=='antec_name_unresolved'
    data=snapshot(app)
    assert data['cameras'][0]['failure_stage']=='engine'
    assert 'camera connection not checked' in data['cameras'][0]['status']
    assert data['cameras'][0]['last_frame'] is None
    assert app.state.store.summary(SID,'red_square','1')['state']=='UNKNOWN'


def test_success_clears_camera_failure_and_reconnect_is_explicit(app,monkeypatch):
    pipeline=app.state.pipeline
    app.state.sampler.failures[SID]=3
    app.state.sampler.source_errors[SID]='worker_unavailable'
    app.state.sampler.request(SID);app.state.sampler.tick(now=100)
    assert app.state.sampler.failures[SID]==0 and SID not in app.state.sampler.source_errors
    calls=[]
    pipeline.auto_worker=SimpleNamespace(last_failure=None,ensure_ready=lambda:calls.append('reconnect'))
    client=TestClient(app)
    assert client.get('/diagnostics',headers=HEADERS).status_code==200 and calls==[]
    assert client.post('/diagnostics/reconnect',headers=HEADERS).status_code==200 and calls==['reconnect']
    assert 'Engine ready' in client.get('/diagnostics?notice=Engine+ready.',headers=HEADERS).text


def test_diagnostics_session_expiry_serializes_and_activity_reports_stage(app):
    app.state.worker_session.process=SimpleNamespace(poll=lambda:None)
    app.state.worker_session.expires_at=utcnow()+timedelta(minutes=15)
    app.state.pipeline.activity={'source_id':SID,'stage':'Answering questions','started_at_utc':utcnow().isoformat()}
    response=TestClient(app).get('/api/v1/diagnostics',headers=HEADERS)
    assert response.status_code==200
    assert response.json()['engine']['session_expires'].endswith('+00:00')
    assert response.json()['activity']['stage']=='Answering questions'


def test_current_scheduler_error_and_camera_test_remain_distinct(app):
    app.state.store.update_source(SID, enabled=True, retain_evidence=False, sample_interval_seconds=1)
    app.state.pipeline.run(SID)
    app.state.sampler.source_errors[SID]='sampling_failed'
    app.state.sampler.last_error='sampling_failed'
    with app.state.store.connection() as db:
        import json
        db.execute('INSERT INTO release_settings VALUES(?,?)',('camera_test:'+SID,json.dumps({'status':'capture_success','checked_at_utc':utcnow().isoformat(),'private_field':'must-not-display'})))
    data=snapshot(app)
    assert data['cameras'][0]['status']=='Last observation failed'
    assert data['cameras'][0]['last_camera_test']['status']=='capture_success'
    assert 'must-not-display' not in str(data)


def test_traffic_lights_distinguish_success_stale_pause_and_failure(app,monkeypatch):
    from bs4 import BeautifulSoup
    app.state.sampler.thread=SimpleNamespace(is_alive=lambda:True)
    app.state.reliable.thread=SimpleNamespace(is_alive=lambda:True)
    app.state.actions.thread=SimpleNamespace(is_alive=lambda:True)
    app.state.store.update_source(SID,enabled=True,retain_evidence=False,sample_interval_seconds=1)
    app.state.pipeline.run(SID)
    assert snapshot(app)['overall']=='green'
    response=TestClient(app).get('/diagnostics',headers=HEADERS)
    page=BeautifulSoup(response.text,'html.parser')
    assert page.select_one('.diagnostic-summary .diagnostic-signal.green[role=status]')
    lights=page.select_one('.diagnostic-summary .signal-lights')
    assert len(lights.select('.signal-lamp'))==3 and len(lights.select('.lit'))==1
    assert lights.select_one('.green.lit') and lights['aria-hidden']=='true'
    assert page.select_one('.diagnostic-summary [aria-label]').get('aria-label').startswith('Green:')
    future=utcnow()+timedelta(seconds=90)
    monkeypatch.setattr('vop.diagnostics.utcnow',lambda:future)
    assert snapshot(app)['cameras'][0]['light']=='amber'
    assert snapshot(app)['overall']=='amber'
    app.state.pipeline.save_capture_error(app.state.pipeline.source(SID),ProviderError('capture_open_failed','test'))
    assert snapshot(app)['cameras'][0]['light']=='red' and snapshot(app)['overall']=='red'
    app.state.store.update_source(SID,enabled=True,retain_evidence=False,sample_interval_seconds=0)
    assert snapshot(app)['cameras'][0]['light']=='amber'
