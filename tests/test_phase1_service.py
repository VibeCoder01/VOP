from dataclasses import replace
import json
from pathlib import Path
from threading import Event, Thread

import pytest
from starlette.testclient import TestClient

from vop.config import load_config
from vop.contracts import ProviderError, Status
from vop.inference.mock import MockInferenceEngine
from vop.service import create_app

TOKEN = "offline-test-secret-" + "x" * 32
HEADERS = {"Authorization": "Bearer " + TOKEN}
SCENE = Path(__file__).resolve().parents[1] / "fixtures" / "scene.png"


@pytest.fixture
def settings(tmp_path):
    data = json.loads((SCENE.parents[1] / "sample-config" / "phase1.json").read_text(encoding="utf-8"))
    data["database"] = "observations.sqlite3"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return load_config(path)


def test_full_synthetic_capture_persist_api_restart(settings):
    with TestClient(create_app(settings, token=TOKEN), headers=HEADERS) as client:
        response = client.post("/api/v1/sources/synthetic-scene/capture")
        assert response.status_code == 201, response.text
        result = response.json()["result"]
        assert result["status"] == "success" and result["synthetic"] and len(result["answers"]) == 3
        assert result["frame_id"] and result["captured_at_utc"] <= result["processed_at_utc"]
        observations = client.get("/api/v1/observations").json()["observations"]
        assert len(observations) == 3
        assert len({o["provenance"]["frame_id"] for o in observations}) == 1
        assert observations[0]["normalised_state"] == "positive"
        assert observations[1]["normalised_state"] == "not_applicable"
        assert client.get("/api/v1/health").json()["observation_count"] == 3
        assert client.get("/api/v1/sources").json()["sources"][0]["status"] == "HEALTHY"
        html = client.get('/').text
        assert '<script src="/ui/actions.js" defer></script>' in html and 'VOP' in html
        assert '<script>' not in html
    with TestClient(create_app(settings, token=TOKEN), headers=HEADERS) as restarted:
        assert len(restarted.get("/api/v1/observations").json()["observations"]) == 3
    database_bytes = settings.database.read_bytes()
    assert TOKEN.encode() not in database_bytes and SCENE.read_bytes() not in database_bytes


@pytest.mark.parametrize("path", ["/", "/api/v1/health", "/api/v1/sources", "/api/v1/observations", "/anything"])
def test_every_route_requires_authentication_and_denials_audited(settings, path):
    app = create_app(settings, token=TOKEN)
    with TestClient(app) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    with app.state.store.connection() as connection:
        # Repeated denials are coalesced for one minute to bound background writes.
        assert connection.execute("SELECT count(*) FROM audit WHERE outcome='denied'").fetchone()[0] == 1


@pytest.mark.parametrize("token", ["", "weak", "a" * 31, "a " * 20, "é" * 40])
def test_no_default_or_weak_secret(settings, token):
    with pytest.raises(ValueError, match="VOP_API_TOKEN"):
        create_app(settings, token=token)


def test_health_reports_camera_setup_without_opening_camera_or_exposing_details(settings, monkeypatch):
    from vop.config import SourceSpec
    app = create_app(settings, token=TOKEN)
    app.state.pipeline.sources['saved-camera'] = SourceSpec('saved-camera', 'Test', 'snapshot', {'endpoint_secret_ref': 'private-ref'}, ())
    def fail(source):
        raise ProviderError('secret_unavailable', 'private-details')
    monkeypatch.setattr('vop.ui_readiness.camera_endpoint', fail)
    with TestClient(app, headers=HEADERS) as client:
        result = client.get('/api/v1/health')
        assert result.json()['camera_setup'] == {'saved-camera': {'ready': False}}
        assert 'private-ref' not in result.text and 'private-details' not in result.text
        monkeypatch.setattr('vop.ui_readiness.camera_endpoint', lambda source: 'http://unused.invalid/image')
        assert client.get('/api/v1/health').json()['camera_setup'] == {'saved-camera': {'ready': True}}


def test_duplicate_ingestion_idempotent_and_conflict_not_overwritten(settings):
    app = create_app(settings, token=TOKEN)
    with TestClient(app, headers=HEADERS) as client:
        headers = {"Content-Type": "image/png", "X-Frame-ID": "frame-1"}
        first = client.post("/api/v1/sources/synthetic-scene/frames", content=SCENE.read_bytes(), headers=headers)
        second = client.post("/api/v1/sources/synthetic-scene/frames", content=SCENE.read_bytes(), headers=headers)
        assert first.status_code == 201 and second.status_code == 200
        assert first.json()["run_id"] == second.json()["run_id"] and second.json()["duplicate"]
        assert client.get("/api/v1/health").json()["observation_count"] == 3
        from PIL import Image
        from io import BytesIO
        buffer = BytesIO()
        Image.new("RGB", (4, 4), "black").save(buffer, format="PNG")
        conflict = client.post("/api/v1/sources/synthetic-scene/frames", content=buffer.getvalue(), headers=headers)
        assert conflict.status_code == 409


def test_capture_failure_persisted_without_frame_or_negative(settings):
    class Broken:
        def capture(self, source):
            raise ProviderError("disconnected", "PRIVATE CAMERA SECRET")
    with TestClient(create_app(settings, token=TOKEN, capture=Broken()), headers=HEADERS) as client:
        result = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        assert result["frame_id"] is None and result["captured_at_utc"] is None
        assert "PRIVATE" not in json.dumps(result)
        rows = client.get("/api/v1/observations").json()["observations"]
        assert len(rows) == 3 and all(o["answer"]["value"] is None and o["normalised_state"] == "error" for o in rows)
        assert client.get("/api/v1/sources").json()["sources"][0]["status"] == "DISCONNECTED"


def test_corrupt_ingestion_recorded_as_error(settings):
    with TestClient(create_app(settings, token=TOKEN), headers=HEADERS) as client:
        response = client.post("/api/v1/sources/synthetic-scene/frames", content=b"corrupt", headers={"Content-Type": "image/png"})
        assert response.status_code == 422
        assert response.json()["result"]["error"]["code"] == "image_corrupt"
        assert all(o["answer"]["value"] is None for o in client.get("/api/v1/observations").json()["observations"])


def test_engine_interchange_and_failures_persist(settings):
    class Broken(MockInferenceEngine):
        def infer(self, request):
            raise TimeoutError("model late")
    engine = Broken({}, "alternate-test-engine")
    with TestClient(create_app(settings, token=TOKEN, engine=engine), headers=HEADERS) as client:
        result = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        assert result["engine_id"] == "alternate-test-engine" and result["status"] == "timeout"
        assert all(a["value"] is None for a in result["answers"])
        assert client.get("/api/v1/sources").json()["sources"][0]["status"] == "HEALTHY"  # capture succeeded; engine did not


def test_wrong_provider_provenance_never_confirmed(settings):
    class Wrong(MockInferenceEngine):
        def infer(self, request):
            return replace(super().infer(request), frame_id="wrong-frame")
    with TestClient(create_app(settings, token=TOKEN, engine=Wrong(settings.mock_answers)), headers=HEADERS) as client:
        result = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        assert result["status"] == "model_failure" and result["error"]["code"] == "provider_contract"
        assert all(a["value"] is None for a in result["answers"])


def test_busy_inference_rejects_second_frame_but_health_responds(settings):
    entered, release = Event(), Event()
    class Slow(MockInferenceEngine):
        def infer(self, request):
            entered.set()
            assert release.wait(5)
            return super().infer(request)
    app = create_app(settings, token=TOKEN, engine=Slow(settings.mock_answers))
    with TestClient(app, headers=HEADERS) as client:
        outcomes = []
        thread = Thread(target=lambda: outcomes.append(client.post("/api/v1/sources/synthetic-scene/capture")))
        thread.start()
        try:
            assert entered.wait(5)
            assert client.get("/api/v1/health").json()["in_flight"]
            assert client.post("/api/v1/sources/synthetic-scene/capture").status_code == 429
        finally:
            release.set()
            thread.join(5)
        assert outcomes[0].status_code == 201
        assert client.get("/api/v1/health").json()["skipped_requests"] == 1


def test_pagination_and_unknown_source_and_cors(settings):
    with TestClient(create_app(settings, token=TOKEN), headers=HEADERS) as client:
        client.post("/api/v1/sources/synthetic-scene/capture")
        first = client.get("/api/v1/observations?limit=2").json()
        second = client.get(f"/api/v1/observations?after={first['next_after']}").json()
        assert len(first["observations"]) == 2 and len(second["observations"]) == 1
        assert client.get("/api/v1/observations?limit=101").status_code == 400
        assert client.get("/api/v1/observations?after=-1").status_code == 400
        assert client.post("/api/v1/sources/unknown/capture").status_code == 404
        assert client.get("/api/v1/health", headers={"Origin": "https://untrusted.example"}).status_code == 403
        assert client.post("/api/v1/sources/synthetic-scene/frames", json={"url": "arbitrary"}).status_code == 415


def test_source_settings_never_exported(settings):
    source = replace(settings.sources[0], kind="snapshot", settings={"endpoint_env": "PRIVATE_ENDPOINT", "allowed_hosts": ["private.example"]})
    with TestClient(create_app(replace(settings, sources=(source,)), token=TOKEN), headers=HEADERS) as client:
        exported = client.get("/api/v1/sources").text
        assert "private.example" not in exported and "PRIVATE_ENDPOINT" not in exported
        denied = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        assert denied["error"]["code"] == "live_consent_required"


def test_untyped_engine_result_stored_as_failure(settings):
    class Wrong(MockInferenceEngine):
        def infer(self, request):
            return {"answer": False}
    with TestClient(create_app(settings, token=TOKEN, engine=Wrong({})), headers=HEADERS) as client:
        result = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        assert result["status"] == "model_failure" and result["error"]["code"] == "provider_contract"
        assert all(a["value"] is None for a in result["answers"])


def test_soft_inference_deadline_discards_late_answers(settings):
    import time
    class Late(MockInferenceEngine):
        def infer(self, request):
            time.sleep(0.03)
            return super().infer(request)
    settings = replace(settings, inference_timeout_seconds=0.01)
    with TestClient(create_app(settings, token=TOKEN, engine=Late(settings.mock_answers)), headers=HEADERS) as client:
        result = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        assert result["status"] == "timeout" and all(a["value"] is None for a in result["answers"])


def test_declared_capability_shortfall_never_calls_engine(settings):
    from vop.contracts import AnswerKind
    class Limited(MockInferenceEngine):
        def infer(self, request):
            raise AssertionError("Unsupported request must not run")
    with TestClient(create_app(settings, token=TOKEN, engine=Limited({}, supported=(AnswerKind.BINARY,))), headers=HEADERS) as client:
        result = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        assert result["status"] == "unsupported" and all(a["value"] is None for a in result["answers"])


def test_storage_failure_visible_and_no_false_success(settings, monkeypatch):
    import sqlite3
    app = create_app(settings, token=TOKEN)
    def broken_save(*args, **kwargs):
        raise sqlite3.OperationalError("disk full")
    monkeypatch.setattr(app.state.store, "save", broken_save)
    with TestClient(app, headers=HEADERS) as client:
        response = client.post("/api/v1/sources/synthetic-scene/capture")
        assert response.status_code == 503 and response.json()["error"] == "storage_unavailable"
        assert client.get("/api/v1/health").json()["observation_count"] == 0


def test_invalid_source_adapter_result_persisted_as_error(settings):
    class Wrong:
        def capture(self, source):
            return {"pixels": "not-a-frame"}
    with TestClient(create_app(settings, token=TOKEN, capture=Wrong()), headers=HEADERS) as client:
        result = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        assert result["frame_id"] is None and result["error"]["code"] == "capture_contract"
        assert all(a["value"] is None for a in result["answers"])
