from dataclasses import replace
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from vop.config import load_config
from vop.measurements import QueryPolicy
from vop.service import create_app
from test_phase2_browser_storage import csrf, login, OWNER


@pytest.fixture
def settings(tmp_path):
    body = json.loads((Path(__file__).resolve().parents[1] / "sample-config" / "phase1.json").read_text(encoding="utf-8"))
    body["database"] = "controls.sqlite3"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return load_config(path)


def test_disable_source_records_gap_and_restart_does_not_reenable(settings):
    app = create_app(settings, token=OWNER)
    with TestClient(app) as client:
        value = login(client)
        for _ in range(2):
            client.post("/ui/sources/synthetic-scene/capture", data={"csrf": value})
        assert app.state.store.summary("synthetic-scene", "red_square", "1")["state"] == "ACTIVE"
        response = client.post("/ui/sources/synthetic-scene", data={"csrf": value, "sample_interval_seconds": "0"})
        assert response.status_code == 200
        assert app.state.store.summary("synthetic-scene", "red_square", "1")["state"] == "UNKNOWN"
        assert app.state.store.events()[0]["ended_at_utc"] is None
    restarted = create_app(settings, token=OWNER)
    assert not restarted.state.store.source_control("synthetic-scene")["enabled"]


def test_repeated_demo_after_capture_uses_ordered_frames(settings):
    app = create_app(settings, token=OWNER)
    with TestClient(app) as client:
        value = login(client)
        client.post("/ui/sources/synthetic-scene/capture", data={"csrf": value})
        for _ in range(2):
            assert client.post("/ui/sources/synthetic-scene/demo", data={"csrf": value}).status_code == 200
        events = app.state.store.events()
        assert len(events) == 2 and all(e["status"] == "closed" for e in events)


def test_browser_metric_range_and_timezone_validate(settings):
    with TestClient(create_app(settings, token=OWNER)) as client:
        login(client)
        assert client.get("/?view=metrics&from=2026-10-13&through=2026-10-13&timezone=UTC").status_code == 200
        assert client.get("/?view=metrics&from=2026-10-14&through=2026-10-13").status_code == 400
        assert client.get("/?view=metrics&from=not-a-date").status_code == 400


def test_query_supersession_keeps_event_history_without_negative_closure(settings):
    app = create_app(settings, token=OWNER)
    app.state.pipeline.run("synthetic-scene")
    app.state.pipeline.run("synthetic-scene")
    record = app.state.store.questions("synthetic-scene")[0]
    app.state.store.edit_question("synthetic-scene", replace(record["spec"], text="New wording"), QueryPolicy(), expected_version="1")
    event = app.state.store.events()[0]
    assert event["status"] == "superseded" and event["ended_at_utc"] is None
    app.state.store.replay_all()
    assert app.state.store.events()[0] == event
