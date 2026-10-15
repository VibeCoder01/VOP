"""Automated desktop workflow without real SSH, model weights or cameras."""
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER, TOKEN
from vop.contracts import ProviderError
from vop.inference.liquid_d1 import CHECKPOINT_REVISION
from vop.inference.remote import RemoteInferenceEngine
from vop.operator_workflow import AutoWorker

PROFILE = {'kind': 'worker', 'id': 'liquid-d1-3b', 'version': CHECKPOINT_REVISION,
           'worker_id': 'antec-d1', 'url': 'http://127.0.0.1:8878', 'secret_ref': 'antec-worker',
           'transport': 'ssh', 'synthetic': False}


class Session:
    def __init__(self, active=False):
        self.active, self.starts, self.stops = active, [], 0
    def status(self): return {'active': self.active}
    def start(self, minutes): self.active = True; self.starts.append(minutes)
    def stop(self): self.active = False; self.stops += 1


def workflow(app, monkeypatch, outcomes, *, active=False, seconds=1):
    engine = RemoteInferenceEngine(PROFILE)
    app.state.pipeline.engine = engine
    session = Session(active)
    calls = []
    def health():
        value = outcomes.pop(0)
        if isinstance(value, Exception): raise value
        return value
    def ssh(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(stdout=TOKEN.encode(), returncode=0)
    monkeypatch.setattr(engine, 'health', health)
    monkeypatch.setattr('vop.operator_workflow.shutil.which', lambda _: 'trusted-ssh')
    monkeypatch.setattr('vop.operator_workflow.subprocess.run', ssh)
    auto = AutoWorker(app.state.pipeline, session, app.state.store, wait_seconds=seconds)
    return engine, session, auto, calls


def test_saved_worker_is_reused_without_start_or_ssh(app, monkeypatch):
    engine, session, auto, calls = workflow(app, monkeypatch, [{'ready': True}])
    auto.ensure_ready()
    assert engine.allow_remote and not session.starts and not calls


def test_reboot_recovery_gets_existing_key_and_starts_one_bounded_session(app, monkeypatch):
    engine, session, auto, calls = workflow(app, monkeypatch,
        [ProviderError('secret_unavailable', 'unavailable'), ProviderError('worker_unavailable', 'disconnected'), {'ready': True}])
    auto.ensure_ready()
    assert session.starts == [15] and engine.allow_remote
    assert engine.secrets.get('antec-worker') == TOKEN
    assert len(calls) == 1 and 'StrictHostKeyChecking=yes' in calls[0] and calls[0][-2] == 'antec.local'


def test_repaired_key_reuses_existing_worker_without_pausing_workload(app, monkeypatch):
    engine, session, auto, calls = workflow(app, monkeypatch, [ProviderError('worker_auth', 'rejected'), {'ready': True}])
    auto.ensure_ready()
    assert not session.starts and len(calls) == 1 and engine.allow_remote


def test_active_session_is_reused_and_slow_start_is_bounded(app, monkeypatch):
    _, session, auto, _ = workflow(app, monkeypatch, [ProviderError('worker_unavailable', 'disconnected'), {'ready': True}], active=True)
    auto.ensure_ready()
    assert not session.starts
    _, session, auto, _ = workflow(app, monkeypatch, [ProviderError('worker_unavailable', 'disconnected')], seconds=0)
    with pytest.raises(ProviderError, match='still getting ready'):
        auto.ensure_ready()
    with pytest.raises(ProviderError): auto.ensure_ready()
    assert session.starts == [15] and session.stops == 0


def test_failed_owned_session_restores_workload_and_identity_is_not_bypassed(app, monkeypatch):
    _, session, auto, _ = workflow(app, monkeypatch, [ProviderError('worker_unavailable', 'disconnected'), {'ready': False, 'error': 'gpu_capacity'}])
    with pytest.raises(ProviderError): auto.ensure_ready()
    assert session.stops == 1
    _, session, auto, calls = workflow(app, monkeypatch, [ProviderError('worker_identity', 'different worker')])
    with pytest.raises(ProviderError): auto.ensure_ready()
    assert not session.starts and not calls


def test_launch_ticket_is_authenticated_single_use_and_never_the_operator_key(app):
    with TestClient(app) as launcher, TestClient(app) as browser:
        assert launcher.post('/api/v1/browser-ticket').status_code == 401
        assert launcher.post('/api/v1/browser-ticket', headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        response = launcher.post('/api/v1/browser-ticket', headers={'Authorization': 'Bearer ' + OWNER})
        path = response.json()['url']
        assert OWNER not in path
        assert browser.get(path).status_code == 200
        assert browser.get('/api/v1/health').status_code == 200
        assert browser.get(path).status_code == 401


def test_expired_launch_ticket_cannot_sign_in(app, monkeypatch):
    with TestClient(app) as client:
        path = client.post('/api/v1/browser-ticket', headers={'Authorization': 'Bearer ' + OWNER}).json()['url']
        monkeypatch.setattr('vop.operator_workflow.monotonic', lambda: float('inf'))
        assert client.get(path).status_code == 401
        assert client.get('/api/v1/health').status_code == 401


def test_automatic_failure_prevents_acquisition_and_offers_retry(app, monkeypatch):
    from vop.service import create_app
    auto_app = create_app(app.state.pipeline.settings, token=OWNER, auto_recover=True)
    def cannot_connect(): raise ProviderError('worker_unavailable', 'connection failed')
    monkeypatch.setattr(auto_app.state.pipeline.auto_worker, 'ensure_ready', cannot_connect)
    monkeypatch.setattr(auto_app.state.pipeline.capture_adapter, 'capture', lambda _: pytest.fail('Must recover before acquisition'))
    with TestClient(auto_app) as client:
        csrf = login(client)
        page = client.post('/ui/sources/synthetic-scene/capture', data={'csrf': csrf})
        assert 'Retry automatically' in page.text and 'Antec is not reachable' in page.text
        assert all(o['answer']['value'] is None for o in auto_app.state.store.observations())
        assert auto_app.state.store.observations()


def test_camera_add_generates_id_enables_and_checks_once_without_inference(app, monkeypatch):
    from dataclasses import replace
    from vop.service import create_app
    from vop.inputs.sources import SourceAdapters, capture_inline
    auto_app = create_app(app.state.pipeline.settings, token=OWNER, auto_recover=True)
    frame = capture_inline(app.state.pipeline.sources['synthetic-scene'])
    captures = []
    def capture(self, source):
        captures.append(source.source_id)
        return replace(frame, source_id=source.source_id)
    monkeypatch.setattr(SourceAdapters, 'capture', capture)
    monkeypatch.setattr(auto_app.state.pipeline.engine, 'infer', lambda _: pytest.fail('Camera check must not infer'))
    with TestClient(auto_app) as client:
        csrf = login(client)
        result = client.post('/integration/camera', data={'csrf': csrf, 'source_id': '', 'model': 'C200',
                    'endpoint': 'rtsp://192.168.1.100:554/stream1', 'username': 'offline-user', 'password': 'offline-password', 'connect': '1'})
        assert 'Capture succeeded' in result.text
        assert captures == ['tapo-c200'] and auto_app.state.store.source_control('tapo-c200')['enabled']
        page = client.get('/cameras/tapo-c200').text
        assert 'Use this camera' in page and 'Edit camera' in page
        assert 'Worker access key' not in page
        assert auto_app.state.store.health()['observation_count'] == 0


def test_question_id_is_generated_and_antec_preset_persists(app):
    from vop.service import create_app
    auto_app = create_app(app.state.pipeline.settings, token=OWNER, auto_recover=True)
    with TestClient(auto_app) as client:
        csrf = login(client)
        body = {'csrf': csrf, 'question_id': '', 'text': 'Is a cat visible?', 'kind': 'binary', 'max_gap_seconds': '60'}
        assert client.post('/ui/questions/synthetic-scene/new', data=body).status_code == 200
        assert client.post('/ui/questions/synthetic-scene/new', data=body).status_code == 200
        ids = {r['spec'].question_id for r in auto_app.state.store.questions('synthetic-scene')}
        assert 'is_a_cat_visible' in ids and 'is_a_cat_visible_2' in ids
        assert client.post('/integration/engine/antec', data={'csrf': csrf}).status_code == 200
        assert auto_app.state.pipeline.engine.config == PROFILE
    fresh = create_app(app.state.pipeline.settings, token=OWNER)
    assert fresh.state.pipeline.engine.config == PROFILE


def test_launcher_opens_ticket_without_exposing_operator_key(monkeypatch):
    import json
    from tools.run_dashboard import open_workspace
    calls = []
    class Connection:
        def __init__(self, *args, **kwargs): pass
        def request(self, method, path, headers):
            assert method == 'POST' and path == '/api/v1/browser-ticket'
            assert headers['Authorization'] == 'Bearer ' + OWNER
        def getresponse(self): return SimpleNamespace(status=200, read=lambda _: json.dumps({'url': '/launch/one-use-ticket'}).encode())
        def close(self): pass
    monkeypatch.setattr('tools.run_dashboard.http.client.HTTPConnection', Connection)
    monkeypatch.setattr('tools.run_dashboard.trusted_listener', lambda _: True)
    monkeypatch.setattr('tools.run_dashboard.webbrowser.open', lambda url: calls.append(url))
    open_workspace(8765, OWNER)
    assert calls == ['http://127.0.0.1:8765/launch/one-use-ticket'] and OWNER not in calls[0]


def test_busy_worker_does_not_trigger_pause_or_acquisition(app, monkeypatch):
    _, session, auto, calls = workflow(app, monkeypatch, [{'ready': True, 'busy': True}])
    with pytest.raises(ProviderError) as failure: auto.ensure_ready()
    assert failure.value.code == 'overloaded' and not session.starts and not calls


def test_untrusted_listener_never_receives_login_key(monkeypatch):
    from tools.run_dashboard import open_workspace
    monkeypatch.setattr('tools.run_dashboard.trusted_listener', lambda _: False)
    monkeypatch.setattr('tools.run_dashboard.http.client.HTTPConnection', lambda *args, **kwargs: pytest.fail('Must not send a key to an untrusted listener'))
    with pytest.raises(OSError): open_workspace(8765, OWNER)


def test_browser_ticket_can_open_while_capture_is_busy(app):
    # Pipeline admission remains occupied, but signing in must not interrupt or wait for capture.
    app.state.pipeline.busy.acquire()
    try:
        with TestClient(app) as client:
            response = client.post('/api/v1/browser-ticket', headers={'Authorization': 'Bearer ' + OWNER})
            assert response.status_code == 200
    finally:
        app.state.pipeline.busy.release()


def test_one_click_monitoring_persists_and_pause_keeps_manual_source_enabled(app):
    from vop.service import create_app
    auto_app = create_app(app.state.pipeline.settings, token=OWNER, auto_recover=True)
    with TestClient(auto_app) as client:
        csrf = login(client)
        auto_app.state.sampler.stop()
        assert client.post('/ui/sources/synthetic-scene/monitor', data={'csrf': csrf, 'mode': 'start'}).status_code == 200
        assert auto_app.state.store.source_control('synthetic-scene')['sample_interval_seconds'] == 10
        auto_app.state.store.update_source('synthetic-scene', enabled=True, retain_evidence=False, sample_interval_seconds=47)
        assert client.post('/ui/sources/synthetic-scene/monitor', data={'csrf': csrf, 'mode': 'pause'}).status_code == 200
        assert client.post('/ui/sources/synthetic-scene/monitor', data={'csrf': csrf, 'mode': 'start'}).status_code == 200
        assert auto_app.state.store.source_control('synthetic-scene')['sample_interval_seconds'] == 47
        assert client.post('/ui/sources/synthetic-scene/monitor', data={'csrf': csrf, 'mode': 'pause'}).status_code == 200
        control = auto_app.state.store.source_control('synthetic-scene')
        assert control['enabled'] and control['sample_interval_seconds'] == 0
    fresh = create_app(app.state.pipeline.settings, token=OWNER)
    assert fresh.state.store.source_control('synthetic-scene')['sample_interval_seconds'] == 0


def test_enable_and_observe_is_one_action_without_resuming_saved_sampling(app):
    from vop.service import create_app
    auto_app = create_app(app.state.pipeline.settings, token=OWNER, auto_recover=True)
    auto_app.state.store.update_source('synthetic-scene', enabled=False, retain_evidence=False, sample_interval_seconds=47)
    with TestClient(auto_app) as client:
        csrf = login(client)
        assert 'Enable and observe' in client.get('/').text
        result = client.post('/ui/sources/synthetic-scene/enable-observe', data={'csrf': csrf})
        assert 'Observation complete' in result.text
        control = auto_app.state.store.source_control('synthetic-scene')
        assert control['enabled'] and control['sample_interval_seconds'] == 0
