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
    return re.search(r'name="csrf"[^>]*value="([^"]+)"', client.get("/integration").text)[1]


def test_gui_protected_camera_retry_profile_restart_and_viewer_denial(app):
    with TestClient(app) as client:
        assert client.get("/integration", headers={"Authorization": "Bearer " + VIEWER}).status_code == 403
        csrf = login(client)
        body = {"csrf": csrf, "source_id": "tapo-c200", "model": "C200", "endpoint": "rtsp://192.168.1.100:554/stream1", "username": "camerauser", "password": "offline-camera-test-secret"}
        assert client.post("/integration/camera", data=body).status_code == 200
        body["password"] = "corrected-offline-camera-secret"
        assert client.post("/integration/camera", data=body).status_code == 200
        assert client.post("/integration/cameras/tapo-c200/test", data={"csrf": csrf}).status_code == 400
        with app.state.store.connection() as db:
            strings = " ".join(str(tuple(row)) for table in ("release_settings", "sources", "audit") for row in db.execute("SELECT * FROM " + table))
        assert "offline-camera-test-secret" not in strings and "corrected-offline-camera-secret" not in strings
        source = app.state.pipeline.sources["tapo-c200"]
        assert source.questions[0].text == "Is there a human in the picture?"
        assert not app.state.store.source_control(source.source_id)["enabled"]
        from vop.reliable import configuration
        exported = configuration(app.state.pipeline.settings, app.state.store, app.state.reliable)
        assert any(s["id"] == "tapo-c200" for s in exported["config"]["sources"])
        engine_body = {"csrf": csrf, "kind": "worker", "engine_id": "liquid-d1-3b", "version": CHECKPOINT_REVISION, "worker_id": "antec-d1", "url": "http://127.0.0.1:8878", "secret_ref": "antec-worker", "transport": "ssh", "worker_token": TOKEN, "remote_consent": "on"}
        assert client.post("/integration/engine", data=engine_body).status_code == 200
        assert app.state.pipeline.engine.allow_remote
    restarted = create_app(app.state.pipeline.settings, token=OWNER)
    assert isinstance(restarted.state.pipeline.engine, RemoteInferenceEngine)
    assert not restarted.state.pipeline.engine.allow_remote
    assert "tapo-c200" in restarted.state.pipeline.sources


def test_camera_connection_form_uses_fixture_and_never_transmits_to_engine(app, monkeypatch):
    from vop.inputs.sources import SourceAdapters, capture_inline
    with TestClient(app) as client:
        csrf = login(client)
        body = {"csrf": csrf, "source_id": "tapo-c210", "model": "C210", "endpoint": "rtsp://192.168.1.101:554/stream2", "username": "offline-user", "password": "offline-fake-password"}
        assert client.post("/integration/camera", data=body).status_code == 200
        frame = capture_inline(app.state.pipeline.sources["synthetic-scene"])
        monkeypatch.setattr(SourceAdapters, "capture", lambda self, source: replace(frame, source_id=source.source_id))
        monkeypatch.setattr(app.state.pipeline.engine, "infer", lambda request: (_ for _ in ()).throw(AssertionError("Connection preview must not call inference")))
        page = client.post("/integration/cameras/tapo-c210/test", data={"csrf": csrf, "capture_consent": "on"})
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


@pytest.mark.skipif(__import__('os').name != 'nt', reason="Windows DPAPI hardware/OS-specific")
def test_actual_windows_dpapi_round_trip_without_plaintext(tmp_path):
    store = SecretStore(tmp_path)
    store.set("offline-test", "dpapi-test-value")
    assert store.get("offline-test") == "dpapi-test-value"
    assert b"dpapi-test-value" not in (tmp_path / "offline-test.dpapi").read_bytes()
