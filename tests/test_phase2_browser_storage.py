from dataclasses import replace
from datetime import timedelta
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3

from PIL import Image
import pytest
from starlette.testclient import TestClient

from vop.config import load_config
from vop.contracts import QuestionSpec, utcnow
from vop.inference.mock import MockInferenceEngine
from vop.inputs.sources import capture_inline
from vop.measurements import QueryPolicy
from vop.preprocessing import preprocess
from vop.service import create_app
from vop.storage import Store, SCHEMA

OWNER = "phase2-owner-offline-test-" + "o" * 32
VIEWER = "phase2-viewer-offline-test-" + "v" * 32
HEADERS = {"Authorization": "Bearer " + OWNER}


@pytest.fixture
def settings(tmp_path):
    body = json.loads((Path(__file__).resolve().parents[1] / "sample-config" / "phase1.json").read_text(encoding="utf-8"))
    body["database"] = "phase2.sqlite3"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return load_config(path)


def csrf(client, route="/login"):
    html = client.get(route).text
    match = re.search(r'name="csrf"[^>]*value="([^"]+)"', html)
    assert match, html
    return match[1]


def login(client, key=OWNER):
    value = csrf(client)
    response = client.post("/login", data={"csrf": value, "access_key": key})
    assert response.status_code == 200 and "Overview" in response.text
    return csrf(client, "/")


def test_browser_login_cookie_csrf_logout_and_host_policy(settings):
    with TestClient(create_app(settings, token=OWNER)) as client:
        assert client.get("/", headers={"Accept": "text/html"}).url.path == "/login"
        assert client.post("/login", data={"access_key": OWNER}).status_code == 403
        value = login(client)
        cookie = client.cookies.get("vop_session")
        assert cookie and OWNER not in cookie
        assert client.post("/ui/sources/synthetic-scene/capture", data={}).status_code == 403
        assert client.post("/ui/sources/synthetic-scene/capture", data={"csrf": value}, headers={"Origin": "https://evil.example"}).status_code == 403
        assert client.post("/ui/sources/synthetic-scene/capture", data={"csrf": value}).status_code == 200
        assert client.post("/logout", data={"csrf": value}).status_code == 200
        assert client.get("/api/v1/health").status_code == 401
        assert client.get("/login", headers={"Host": "evil.example"}).status_code == 400


def test_question_edit_persists_version_and_xss_escaped(settings):
    app = create_app(settings, token=OWNER)
    with TestClient(app) as client:
        value = login(client)
        form = {"csrf": value, "question_id": "red_square", "expected_version": "1", "text": '<img src=x onerror="alert(1)">',
                "kind": "binary", "threshold": "0.7", "positive_confirmations": "2", "negative_confirmations": "2",
                "max_gap_seconds": "60", "unknown_gap_policy": "resume", "roi": "0,0,0.5,1", "enabled": "on", "mock_answer": "true"}
        response = client.post("/ui/questions/synthetic-scene/red_square", data=form)
        assert response.status_code == 200 and "&lt;img" in response.text and '<img src=x' not in response.text
        assert app.state.store.questions("synthetic-scene")[0]["spec"].version == "2"
        assert client.post("/ui/questions/synthetic-scene/red_square", data=form).status_code == 400
    restarted = create_app(settings, token=OWNER)
    assert restarted.state.store.questions("synthetic-scene")[0]["spec"].version == "2"
    assert restarted.state.pipeline.engine.source_answers[("synthetic-scene", "red_square", "2")] is True


def test_episode_replay_and_query_version_isolation(settings):
    engine = MockInferenceEngine(settings.mock_answers)
    app = create_app(settings, token=OWNER, engine=engine)
    pipeline = app.state.pipeline
    start = utcnow() - timedelta(seconds=100)
    for index, value in enumerate((False, True, True, True, False, False)):
        engine.configured["red_square"] = value
        frame = replace(capture_inline(settings.sources[0]), captured_at_utc=start + timedelta(seconds=index * 10))
        pipeline.run("synthetic-scene", frame)
    events = app.state.store.events()
    assert len(events) == 1 and events[0]["status"] == "closed"
    app.state.store.replay_all()
    assert app.state.store.events() == events
    q = app.state.store.questions("synthetic-scene")[0]["spec"]
    new = app.state.store.edit_question("synthetic-scene", replace(q, text="Changed text"), QueryPolicy(), expected_version="1")
    assert new.version == "2"
    assert app.state.store.events()[0]["question_version"] == "1"
    assert app.state.store.summary("synthetic-scene", "red_square", "2")["episode_count"] is None


def test_evidence_default_off_operator_only_and_delete(settings):
    app = create_app(settings, token=OWNER, viewer_token=VIEWER)
    with TestClient(app, headers=HEADERS) as client:
        first = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        frame_id = first["frame_id"]
        url = f"/ui/evidence/synthetic-scene/{frame_id}"
        assert client.get(url).status_code == 404
        app.state.store.update_source("synthetic-scene", enabled=True, retain_evidence=True, sample_interval_seconds=0)
        second = client.post("/api/v1/sources/synthetic-scene/capture").json()["result"]
        frame_id = second["frame_id"]
        url = f"/ui/evidence/synthetic-scene/{frame_id}"
        assert client.get(url).status_code == 200
        assert client.get(url, headers={"Authorization": "Bearer " + VIEWER}).status_code == 403
        assert client.post(url + "/delete", headers={"Authorization": "Bearer " + VIEWER}).status_code == 403
        assert client.post(url + "/delete").status_code == 200
        assert client.get(url).status_code == 404
        assert client.get(f"/ui/preview/synthetic-scene/{frame_id}").status_code == 404


def test_viewer_cannot_edit_or_capture(settings):
    with TestClient(create_app(settings, token=OWNER, viewer_token=VIEWER)) as client:
        value = login(client, VIEWER)
        assert client.get("/ui/questions/synthetic-scene/red_square").status_code == 403
        assert client.post("/ui/sources/synthetic-scene/capture", data={"csrf": value}).status_code == 403
        assert "Read only" in client.get("/?view=questions").text


def test_privacy_masks_precede_crop_and_retention(settings):
    frame = capture_inline(settings.sources[0])
    masked = preprocess(frame, [[0, 0, 0.5, 1]], roi=[0, 0, 0.5, 1])
    with Image.open(BytesIO(masked.payload)) as image:
        assert image.getpixel((50, 80)) == (0, 0, 0)
        assert image.size == (192, 256)
    assert masked.frame_id == frame.frame_id and masked.captured_at_utc == frame.captured_at_utc
    assert masked.sha256 != frame.sha256


def test_schema1_upgrade_preserves_history_and_backup(settings):
    with sqlite3.connect(settings.database) as connection:
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), "legacy", "preserved"))
    store = Store(settings.database)
    assert store.health()["database_schema"] == 3
    backup = settings.database.with_name(settings.database.name + ".v1-backup.sqlite3")
    assert backup.exists()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("SELECT outcome FROM audit").fetchone()[0] == "preserved"


def test_all_views_native_markup_and_no_external_assets(settings):
    with TestClient(create_app(settings, token=OWNER), headers=HEADERS) as client:
        for view in ("overview", "sources", "questions", "events", "metrics"):
            response = client.get("/?view=" + view)
            assert response.status_code == 200
            assert "cdn" not in response.text.lower() and "<script" not in response.text
            assert 'name="viewport"' in response.text
        assert client.get("/api/v1/metrics").json()["metrics"][0]["summary"]["state"] == "UNKNOWN"
        assert client.get("/?view=metrics&timezone=invalid/timezone").status_code == 400


def test_viewer_can_logout_and_cookie_tampering_denied(settings):
    with TestClient(create_app(settings, token=OWNER, viewer_token=VIEWER)) as client:
        value = login(client, VIEWER)
        assert client.post("/logout", data={"csrf": value}).status_code == 200
        assert client.get("/api/v1/health").status_code == 401
        client.cookies.set("vop_session", "tampered-role-operator")
        assert client.get("/api/v1/health").status_code == 401
