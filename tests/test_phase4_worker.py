from dataclasses import asdict, replace
from datetime import timedelta
import json
from pathlib import Path
import re
from threading import Event, Thread

import pytest
from starlette.testclient import TestClient

from vop.config import load_config
from vop.contracts import ProviderError, Status, infer, utcnow
from vop.inference.remote import RemoteInferenceEngine, profile
from vop.inference.liquid_d1 import CHECKPOINT_REVISION
from vop.secrets import SecretStore
from vop.service import create_app
from vop.storage import dumps
from vop.worker import SupervisedEngine, create_worker_app
from vop.worker_protocol import decode_request, decode_result, encode, request_body

TOKEN = "phase4-offline-worker-" + "x" * 32
OWNER, VIEWER = "phase4-offline-owner-" + "o" * 32, "phase4-offline-viewer-" + "v" * 32
PROFILE = {"kind": "worker", "id": "mock-worker", "version": "deterministic-mock-v1", "worker_id": "worker-test", "url": "http://127.0.0.1:8878", "secret_ref": "worker-test", "transport": "local", "synthetic": True}


def mock_worker():
    return SupervisedEngine({"kind": "mock", "engine_id": "mock-worker", "answers": {"red_square": True, "background": "white", "brightness": 2.0}}, timeout_seconds=2)


@pytest.mark.parametrize("field,value", [("value", "false"), ("score", float("inf")), ("calibrated", "false")])
def test_remote_answer_rejects_malformed_typed_values(request_frame, field, value):
    from vop.inference.mock import MockInferenceEngine
    engine = MockInferenceEngine({"red_square": True}, "mock-worker")
    raw = json.loads(encode(infer(engine, request_frame)))
    raw["answers"][0][field] = value
    with pytest.raises(ValueError):
        decode_result(raw, request_frame, engine.engine_id, engine.engine_version)


def test_supervised_real_child_and_restart(request_frame):
    engine = mock_worker()
    try:
        engine.prepare()
        first_pid = engine.process.pid
        assert infer(engine, request_frame).status == Status.SUCCESS
        engine.process.kill()
        engine.process.join()
        engine.timeout_seconds = 5  # Restart includes Windows spawn; hard-deadline cases use their own short budget.
        assert infer(engine, request_frame).status == Status.SUCCESS
        assert engine.process.pid != first_pid
    finally:
        engine.close()


def test_hard_timeout_terminates_child_without_fabricated_value(request_frame, monkeypatch):
    engine = mock_worker()
    engine.prepare()
    pid = engine.process.pid
    original = engine.connection
    class SilentConnection:
        def send(self, value): pass
        def poll(self, seconds): return False
        def close(self): original.close()
    engine.connection = SilentConnection()
    result = infer(engine, request_frame)
    assert result.status == Status.TIMEOUT and all(a.value is None for a in result.answers)
    assert engine.process is None and engine.last_error == "worker_timeout"


def test_actual_slow_mock_child_is_killed_at_deadline(request_frame):
    engine = SupervisedEngine({"kind": "mock", "engine_id": "mock-worker", "answers": {"red_square": True}, "mock_delay_seconds": 2}, timeout_seconds=.1)
    try:
        engine.prepare()
        result = infer(engine, request_frame)
        assert result.status == Status.TIMEOUT and engine.process is None
        assert all(a.value is None for a in result.answers)
    finally:
        engine.close()


def test_worker_auth_digest_idempotency_and_expiry(request_frame):
    engine = mock_worker()
    with TestClient(create_worker_app(engine, worker_id="worker-test", token=TOKEN)) as client:
        headers = {"Authorization": "Bearer " + TOKEN}
        assert client.get("/health").status_code == 401
        assert client.get("/health", headers={**headers, "Origin": "http://evil.invalid"}).status_code == 401
        assert client.get("/health", headers=headers).json()["runtime"]["device"] == "mock"
        body = json.loads(encode(request_body(request_frame, "worker-test")))
        first = client.post("/infer", headers=headers, json=body)
        assert first.status_code == 200 and first.json()["result"]["synthetic"]
        assert client.post("/infer", headers=headers, json=body).json() == first.json()
        body["frame"]["sha256"] = "0" * 64
        assert client.post("/infer", headers=headers, json=body).status_code == 400
        body = json.loads(encode(request_body(request_frame, "worker-test")))
        body["deadline_utc"] = (utcnow() - timedelta(seconds=1)).isoformat()
        assert client.post("/infer", headers=headers, json=body).status_code == 400


def test_remote_consent_identity_and_real_protocol_client(request_frame):
    worker = mock_worker()
    with TestClient(create_worker_app(worker, worker_id="worker-test", token=TOKEN)) as client:
        class Vault:
            def get(self, name): return TOKEN
        class Opener:
            def open(self, req, timeout):
                from io import BytesIO
                route = req.full_url.rsplit(":8878", 1)[-1]
                response = client.request("POST" if req.data else "GET", route, content=req.data, headers=dict(req.header_items()))
                assert response.status_code == 200
                return BytesIO(response.content)
        engine = RemoteInferenceEngine(PROFILE, secrets=Vault(), opener=Opener())
        assert engine.health()["ready"]
        denied = infer(engine, request_frame)
        assert denied.error.code == "remote_consent_required"
        engine.allow_remote = True
        result = infer(engine, request_frame)
        assert result.status == Status.SUCCESS and result.answers[0].value is True
        engine.config["worker_id"] = "wrong"
        with pytest.raises(ProviderError, match="worker_identity"):
            engine.health()


@pytest.mark.parametrize("change", [{"url": "http://192.168.1.1:80"}, {"url": "http://localhost:8878"}, {"url": "http://user:secret@127.0.0.1:8878"}, {"url": "http://127.0.0.1:8878/?token=x"}, {"secret_ref": "../../bad"}, {"transport": "plaintext-lan"}])
def test_profile_trust_boundary(change):
    with pytest.raises(ValueError):
        profile({**PROFILE, **change})


def test_request_identity_separates_roi_and_criteria(request_frame):
    from vop.preprocessing import preprocess
    first = request_body(request_frame, "worker-test")
    cropped = request_body(replace(request_frame, frame=preprocess(request_frame.frame, [], (.0, .0, .5, 1))), "worker-test")
    assert first["request_id"] != cropped["request_id"]
    changed = replace(request_frame, questions=(replace(request_frame.questions[0], text="Different criteria"),))
    assert request_body(changed, "worker-test")["request_id"] != first["request_id"]


def test_stale_frame_and_pixel_metadata_are_rejected(request_frame):
    stale = replace(request_frame, frame=replace(request_frame.frame, captured_at_utc=utcnow()-timedelta(minutes=10)))
    with pytest.raises(ValueError, match="Stale frame"):
        decode_request(json.loads(encode(request_body(stale, "worker-test"))), "worker-test")
    wrong = replace(request_frame, frame=replace(request_frame.frame, width=1, height=1))
    with pytest.raises(ValueError, match="dimensions"):
        decode_request(json.loads(encode(request_body(wrong, "worker-test"))), "worker-test")


@pytest.fixture
def app(tmp_path, monkeypatch):
    values = {}
    def set_secret(self, name, value): values[name] = value
    def get_secret(self, name):
        if name not in values:
            raise ProviderError("secret_unavailable", "No secret")
        return values[name]
    monkeypatch.setattr(SecretStore, "set", set_secret)
    monkeypatch.setattr(SecretStore, "get", get_secret)
    path = tmp_path / "config.json"
    body = json.loads((Path(__file__).resolve().parents[1]/"sample-config/phase1.json").read_text())
    body["database"] = "data/test.sqlite3"
    path.write_text(json.dumps(body))
    return create_app(load_config(path), token=OWNER, viewer_token=VIEWER)


def login(client):
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', client.get("/login").text)[1]
    assert client.post("/login", data={"csrf": token, "access_key": OWNER}).status_code == 200
    token = re.search(r'name="csrf"[^>]*value="([^"]+)"', client.get("/").text)[1]
    assert client.post('/ui/mode', data={'csrf': token, 'mode': 'configure'}).status_code == 200
    return token


def test_gui_protected_camera_retry_profile_restart_and_viewer_denial(app):
    with TestClient(app) as client:
        assert client.get("/integration", headers={"Authorization": "Bearer " + VIEWER}).status_code == 403
        csrf = login(client)
        body = {"csrf": csrf, "source_id": "tapo-c200", "model": "C200", "endpoint": "rtsp://192.168.1.100:554/stream1", "username": "camerauser", "password": "offline-camera-test-secret"}
        assert client.post("/integration/camera", data=body).status_code == 200
        body["password"] = "corrected-offline-camera-secret"
        assert client.post("/integration/camera", data=body).status_code == 200
        assert client.post("/integration/cameras/not-saved/test", data={"csrf": csrf}).status_code == 400
        with app.state.store.connection() as db:
            strings = " ".join(str(tuple(row)) for table in ("release_settings", "sources", "audit") for row in db.execute("SELECT * FROM " + table))
        assert "offline-camera-test-secret" not in strings and "corrected-offline-camera-secret" not in strings
        source = app.state.pipeline.sources["tapo-c200"]
        assert source.questions[0].text == "Is there a human in the picture?"
        assert not app.state.store.source_control(source.source_id)["enabled"]
        from vop.reliable import configuration
        exported = configuration(app.state.pipeline.settings, app.state.store, app.state.reliable)
        assert any(s["id"] == "tapo-c200" for s in exported["config"]["sources"])
        engine_body = {"csrf": csrf, "kind": "worker", "engine_id": "liquid-d1-3b", "version": CHECKPOINT_REVISION, "worker_id": "antec-d1", "url": "http://127.0.0.1:8878", "secret_ref": "antec-worker", "transport": "ssh", "worker_token": TOKEN}
        assert client.post("/integration/engine", data=engine_body).status_code == 200
        assert app.state.pipeline.engine.allow_remote
    restarted = create_app(app.state.pipeline.settings, token=OWNER)
    assert isinstance(restarted.state.pipeline.engine, RemoteInferenceEngine)
    assert not restarted.state.pipeline.engine.allow_remote
    assert "tapo-c200" in restarted.state.pipeline.sources


def test_camera_form_reloads_selected_saved_endpoint_and_never_prefills_password(app):
    def input_value(page, name):
        from html import unescape
        tag = re.search(r'<input\b[^>]*\bname="' + name + r'"[^>]*>', page)[0]
        value = re.search(r'\bvalue="([^"]*)"', tag)
        return unescape(value[1]) if value else ""
    with TestClient(app) as client:
        csrf = login(client)
        for sid, model, address in (("tapo-c200", "C200", "192.168.1.201"), ("tapo-c210", "C210", "192.168.1.202")):
            body = {"csrf": csrf, "source_id": sid, "model": model, "endpoint": "rtsp://" + address + ":554/stream2", "username": sid + "-user", "password": "offline-form-secret"}
            page = client.post("/integration/camera", data=body)
            assert page.status_code == 200 and page.url.params["camera"] == sid
            assert input_value(page.text, "endpoint") == body["endpoint"]
            assert input_value(page.text, "username") == body["username"]
            assert input_value(page.text, "password") == "" and body["password"] not in page.text
        saved = client.get("/integration?camera=tapo-c200")
        assert input_value(saved.text, "endpoint") == "rtsp://192.168.1.201:554/stream2"
        body.update(source_id="tapo-c200", model="C200", endpoint=input_value(saved.text, "endpoint"), password="", username=input_value(saved.text, "username"))
        assert client.post("/integration/camera", data=body).status_code == 200
        new = client.get("/integration?new_camera=1")
        assert input_value(new.text, "endpoint") == "" and input_value(new.text, "source_id") == ""
    restarted = create_app(app.state.pipeline.settings, token=OWNER)
    with TestClient(restarted) as client:
        login(client)
        saved = client.get("/integration?camera=tapo-c210")
        assert input_value(saved.text, "source_id") == "tapo-c210"
        assert input_value(saved.text, "endpoint") == "rtsp://192.168.1.202:554/stream2"
        assert re.search(r'<option(?=[^>]*value="C210")(?=[^>]*selected)[^>]*>', saved.text)


def test_camera_connection_form_uses_fixture_and_never_transmits_to_engine(app, monkeypatch):
    from vop.inputs.sources import SourceAdapters, capture_inline
    with TestClient(app) as client:
        csrf = login(client)
        body = {"csrf": csrf, "source_id": "tapo-c210", "model": "C210", "endpoint": "rtsp://192.168.1.101:554/stream2", "username": "offline-user", "password": "offline-fake-password"}
        assert client.post("/integration/camera", data=body).status_code == 200
        frame = capture_inline(app.state.pipeline.sources["synthetic-scene"])
        monkeypatch.setattr(SourceAdapters, "capture", lambda self, source: replace(frame, source_id=source.source_id))
        monkeypatch.setattr(app.state.pipeline.engine, "infer", lambda request: (_ for _ in ()).throw(AssertionError("Connection preview must not call inference")))
        page = client.post("/integration/cameras/tapo-c210/test", data={"csrf": csrf})
        assert page.status_code == 200 and "No inference was requested" in page.text
        assert app.state.store.health()["observation_count"] == 0
        with app.state.store.connection() as db:
            diag = json.loads(db.execute("SELECT value_json FROM release_settings WHERE id='camera_test:tapo-c210'").fetchone()[0])
        assert diag["status"] == "capture_success" and diag["width"] == frame.width
        assert not app.state.store.source_control("tapo-c210")["enabled"]


def test_busy_camera_test_renders_browser_guidance_and_keeps_api_json(app):
    with TestClient(app) as client:
        csrf = login(client)
        body = {"csrf": csrf, "source_id": "tapo-c200", "model": "C200", "endpoint": "rtsp://192.168.1.100:554/stream1", "username": "offline-user", "password": "offline-fake-password"}
        assert client.post("/integration/camera", data=body).status_code == 200
        app.state.pipeline.busy.acquire()
        try:
            page = client.post("/integration/cameras/tapo-c200/test", data={"csrf": csrf, "capture_consent": "on"}, headers={"Accept": "text/html"})
            assert page.status_code == 429 and "text/html" in page.headers["content-type"]
            assert "Another capture or inference is running" in page.text
            response = client.post("/api/v1/sources/synthetic-scene/capture", headers={"Authorization": "Bearer " + OWNER})
            assert response.status_code == 429 and response.json() == {"error": "overloaded"}
        finally:
            app.state.pipeline.busy.release()


def test_session_buttons_require_real_pilot_profile_without_permission_checkbox(app, monkeypatch):
    started = []
    stopped = []
    monkeypatch.setattr(app.state.worker_session, "start", lambda minutes: started.append(minutes))
    monkeypatch.setattr(app.state.worker_session, "stop", lambda: stopped.append(True))
    with TestClient(app) as client:
        csrf = login(client)
        assert client.post("/integration/session/start", data={"csrf": csrf}).status_code == 400
        assert not started
        body = {"csrf": csrf, "kind": "worker", "engine_id": "liquid-d1-3b", "version": CHECKPOINT_REVISION, "worker_id": "antec-d1", "url": "http://127.0.0.1:8878", "secret_ref": "antec-worker", "transport": "ssh", "worker_token": TOKEN}
        assert client.post("/integration/engine", data=body).status_code == 200
        assert client.post("/integration/session/start", data={"csrf": csrf, "minutes": "30"}).status_code == 200
        assert started == [30] and app.state.pipeline.engine.allow_remote
        assert client.post("/integration/consent", data={"csrf": csrf, "allow": "on"}).status_code == 200
        assert app.state.pipeline.engine.allow_remote
        assert client.post("/integration/consent", data={"csrf": csrf}).status_code == 200
        assert not app.state.pipeline.engine.allow_remote
        assert client.post("/integration/session/stop", data={"csrf": csrf}).status_code == 200
        assert stopped


def test_setup_shows_dependencies_and_has_no_permission_checkboxes(app):
    with TestClient(app) as client:
        login(client)
        page = client.get('/integration').text
        for name in ('pause_consent', 'capture_consent', 'remote_consent', 'allow'):
            assert f'name="{name}"' not in page
        assert 'Open Cameras' in page and 'Open Engines' in page
        assert 'Start antec session' not in page
        assert 'Worker access key' not in page
        engine = client.get('/engines/current').text
        assert 'Check connection' in engine and 'Demo answers are synthetic' in engine


def test_disabled_source_explains_capture_dependency_without_acquisition(app, monkeypatch):
    def must_not_capture(*args):
        pytest.fail('A blocked operation must not acquire an image')
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', must_not_capture)
    app.state.store.update_source('synthetic-scene', enabled=False, retain_evidence=False, sample_interval_seconds=0)
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        page = client.get('/').text
        assert 'Source is disabled' in page and 'Source controls' in page
        assert 'Capture once' not in page
        result = client.post('/ui/sources/synthetic-scene/capture', data={'csrf': csrf})
        assert 'Cannot observe' in result.text and 'No camera image was acquired' in result.text
        assert app.state.store.health()['observation_count'] == 0


def test_unavailable_worker_is_checked_before_camera_and_health_failure_is_visible(app, monkeypatch):
    engine = RemoteInferenceEngine(PROFILE, allow_remote=True)
    app.state.secrets.set(PROFILE['secret_ref'], TOKEN)
    app.state.pipeline.engine = engine
    def not_connected():
        raise ProviderError('worker_unavailable', 'Worker connection failed')
    monkeypatch.setattr(engine, 'health', not_connected)
    def must_not_capture(*args):
        pytest.fail('Worker dependency must be checked before camera acquisition')
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', must_not_capture)
    with TestClient(app) as client:
        csrf = login(client)
        result = client.post('/ui/sources/synthetic-scene/capture', data={'csrf': csrf})
        assert 'Worker check failed (worker_unavailable)' in result.text
        assert 'No camera image was acquired' in result.text
        assert app.state.store.health()['observation_count'] == 0
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        assert 'Worker was unavailable at the last check' in client.get('/').text


def test_no_questions_or_worker_key_explains_action_dependencies(app, monkeypatch):
    from vop.ui_readiness import capture_dependencies
    pipeline, store = app.state.pipeline, app.state.store
    with store.connection() as db:
        db.execute('UPDATE query_controls SET enabled=0')
    messages = str(capture_dependencies(pipeline, 'synthetic-scene'))
    assert 'No enabled questions' in messages
    pipeline.engine = RemoteInferenceEngine(PROFILE)
    assert 'Worker access key is unavailable' in str(capture_dependencies(pipeline, 'synthetic-scene'))


def test_dashboard_launcher_reuses_selected_worker_without_extra_permission_flag(app, monkeypatch):
    import sys
    from tools import run_dashboard
    calls = []
    monkeypatch.setattr(sys, 'argv', ['run_dashboard.py'])
    monkeypatch.setattr(run_dashboard, 'load_config', lambda path: app.state.pipeline.settings)
    monkeypatch.setattr(run_dashboard, 'create_app', lambda settings, **kwargs: calls.append(kwargs) or app)
    monkeypatch.setattr(run_dashboard, 'managed_run', lambda *args, **kwargs: False)
    run_dashboard.main()
    assert calls[0]['allow_remote_inference'] is True
    assert calls[0]['allow_live_sources'] is False


def test_capture_page_gives_plain_answer_and_hides_raw_details(app):
    with TestClient(app) as client:
        csrf = login(client)
        page = client.post("/ui/sources/synthetic-scene/capture", data={"csrf": csrf})
        assert page.status_code == 200 and "Observation complete" in page.text
        assert "Is a red square visible?" in page.text and "Technical details" in page.text
        assert "Capture again" in page.text and "Inference time:" in page.text
        assert re.search(r'<details>\s*<summary>Technical details</summary>', page.text)


@pytest.mark.parametrize('code,status,message', [
    ('capture_timeout', Status.TIMEOUT, 'The camera did not respond in time.'),
    ('capture_open_failed', Status.MODEL_FAILURE, 'The camera could not connect.')])
def test_capture_page_handles_acquisition_failure_without_inference_time(app, monkeypatch, code, status, message):
    def fail(source):
        raise ProviderError(code, 'Fixture acquisition failed', status)
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', fail)
    monkeypatch.setattr(app.state.pipeline.engine, 'infer', lambda *_: pytest.fail('No frame: inference must not run'))
    with TestClient(app) as client:
        csrf = login(client)
        page = client.post('/ui/sources/synthetic-scene/capture', data={'csrf': csrf})
        assert page.status_code == 200
        assert 'No valid answer' in page.text and message in page.text
        assert 'Inference was not run. No image was available.' in page.text
        assert '0.000 seconds' not in page.text
        assert 'Capture again' in page.text and '/ui/sources/synthetic-scene' in page.text
        rows = app.state.store.observations('synthetic-scene')
        assert rows and all(row['normalised_state'] == 'error' for row in rows)
        assert all(row['answer']['value'] is None for row in rows)
        assert app.state.store.summary('synthetic-scene', 'red_square', '1', kind='binary')['state'] == 'UNKNOWN'
        assert all(row['provenance']['elapsed_ms'] is None for row in rows)


@pytest.mark.skipif(__import__('os').name != 'nt', reason="Windows DPAPI hardware/OS-specific")
def test_actual_windows_dpapi_round_trip_without_plaintext(tmp_path):
    store = SecretStore(tmp_path)
    store.set("offline-test", "dpapi-test-value")
    assert store.get("offline-test") == "dpapi-test-value"
    assert b"dpapi-test-value" not in (tmp_path / "offline-test.dpapi").read_bytes()
