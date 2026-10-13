from dataclasses import replace
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import re
import sqlite3

import pytest
from starlette.testclient import TestClient

from vop.config import load_config
from vop.contracts import utcnow
from vop.inputs.sources import capture_inline
from vop.service import create_app
from vop.storage import Store, dumps
from vop.reliable import Reliable, backup, configuration, restore, csv_export

ROOT = Path(__file__).resolve().parents[1]
TOKEN, VIEWER = "phase3-owner-" + "o" * 32, "phase3-viewer-" + "v" * 32
HEADERS = {"Authorization": "Bearer " + TOKEN}
SID, QID = "synthetic-scene", "red_square"


@pytest.fixture
def app(tmp_path):
    body = json.loads((ROOT / "sample-config/phase1.json").read_text(encoding="utf-8"))
    body["database"] = "data/vop.sqlite3"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return create_app(load_config(path), token=TOKEN, viewer_token=VIEWER)


def rule(kind="duration", **changes):
    return {"id": "test-rule", "source_id": SID, "question_id": QID, "kind": kind, "threshold": 3600, **changes}


def samples(app, start, values, step=60):
    pipeline = app.state.pipeline
    frames = []
    for i, value in enumerate(values):
        version = pipeline.store.questions(SID)[0]["spec"].version
        pipeline.engine.configure_source_answer(SID, QID, version, value)
        stamp = start + timedelta(seconds=i * step)
        frame = replace(capture_inline(pipeline.sources[SID]), captured_at_utc=stamp)
        pipeline.run(SID, frame)
        frames.append(frame)
    return frames


def test_one_hour_alert_idempotency_unknown_restart_and_delivery(app):
    engine = app.state.reliable
    start = utcnow() - timedelta(hours=2)
    frames = samples(app, start, [True] * 64)
    engine.save_rule(rule(webhook=True))
    now = frames[-1].captured_at_utc
    engine.evaluate(now)
    engine.evaluate(now)
    alerts = engine.alerts()
    assert len(alerts) == 1 and alerts[0]["payload"]["synthetic"] is True
    alert_id = alerts[0]["id"]
    engine.sender = lambda payload, key: "temporary_failure"
    for i in range(5):
        engine.retry(now + timedelta(seconds=400 * i))
    delivery = next(d for d in engine.alerts()[0]["deliveries"] if d["channel"] == "webhook")
    assert delivery["status"] == "failed" and delivery["attempts"] == 5
    engine.update_alert(alert_id, "acknowledged", "Reviewed mock")
    engine.update_alert(alert_id, "resolved", "Operator resolution")
    with pytest.raises(ValueError):
        engine.update_alert(alert_id, "acknowledged", "")
    app.state.pipeline.record_gap(SID)
    engine.evaluate(utcnow())
    fresh = Reliable(Store(app.state.store.path), engine.settings, app.state.pipeline)
    fresh.evaluate(now)
    assert fresh.alerts()[0]["id"] == alert_id and len(fresh.alerts()) == 1
    assert fresh.alerts()[0]["status"] == "resolved"


def test_duration_does_not_extrapolate_unknown_or_duplicate_after_resume(app):
    engine = app.state.reliable
    engine.save_rule(rule(threshold=0))
    now = utcnow()
    samples(app, now - timedelta(seconds=30), [True, True], step=10)
    engine.evaluate(now)
    assert engine.alerts() == []  # confirming sample opens episode, has no active interval yet
    engine.evaluate(now + timedelta(hours=2))
    assert engine.alerts() == []  # no extrapolation while stale
    samples(app, now - timedelta(seconds=5), [True], step=1)
    engine.evaluate(now)
    assert len(engine.alerts()) == 1
    app.state.pipeline.record_gap(SID)
    engine.evaluate(now + timedelta(seconds=1))
    samples(app, utcnow() + timedelta(seconds=2), [True, True, True], step=1)
    engine.evaluate(utcnow() + timedelta(seconds=5))
    assert len(engine.alerts()) == 1


def test_count_transitions_revision_and_query_version(app):
    engine = app.state.reliable
    engine.save_rule(rule("count", threshold=1, window_seconds=3600))
    now = utcnow()
    samples(app, now - timedelta(seconds=100), [True, True, False, False, True, True, False, False], step=10)
    engine.evaluate(now)
    engine.evaluate(now)
    assert len(engine.alerts()) == 1
    engine.save_rule(rule("count", threshold=1, window_seconds=3600))
    engine.evaluate(now)
    assert len(engine.alerts()) == 2 and {a["rule_revision"] for a in engine.alerts()} == {1, 2}
    store = app.state.store
    record = store.questions(SID)[0]
    store.edit_question(SID, record["spec"], record["policy"])
    engine.evaluate(now)
    assert len(engine.alerts()) == 2  # new version has no old episodes


@pytest.mark.parametrize("changes", [{"threshold": float("nan")}, {"kind": "bad"}, {"enabled": "yes"}, {"question_id": "background"}, {"source_id": "unknown"}, {"threshold": True}, {"unexpected": 1}])
def test_rule_validation(app, changes):
    with pytest.raises(ValueError):
        app.state.reliable.save_rule(rule(**changes))


def test_restart_recovers_sending_with_same_id_and_retry_success(app):
    engine = app.state.reliable
    now = utcnow()
    samples(app, now - timedelta(seconds=30), [True, True, True], step=10)
    engine.save_rule(rule(threshold=0, webhook=True))
    engine.evaluate(now)
    aid = engine.alerts()[0]["id"]
    with app.state.store.connection() as db:
        db.execute("UPDATE deliveries SET status='sending',attempts=1 WHERE channel='webhook'")
    delivered = []
    engine.sender = lambda payload, key: delivered.append(key) or "delivered"
    engine.start()
    engine.stop()
    assert delivered == [aid]
    assert next(d for d in engine.alerts()[0]["deliveries"] if d["channel"] == "webhook")["status"] == "delivered"


def test_exports_permissions_csrf_xss_csv_and_rate_limit(app):
    with TestClient(app) as client:
        assert client.get("/release").status_code == 401
        assert client.get("/release/config", headers={"Authorization": "Bearer " + VIEWER}).status_code == 403
        assert client.post("/release/rules", headers={"Authorization": "Bearer " + VIEWER}).status_code == 403
        assert client.get("/release/export?kind=events&format=csv", headers=HEADERS).status_code == 200
        assert client.get("/release/export?source=missing", headers=HEADERS).status_code == 400
        assert client.post("/release/rules", data={}).status_code in (401, 403)
        html = client.get("/login").text
        csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', html)[1]
        assert client.post("/login", data={"csrf": csrf, "access_key": TOKEN}).status_code == 200
        assert client.post("/release/rules", data={}).status_code == 403
        html = client.get("/release?notice=%3Cscript%3Ebad%3C/script%3E").text
        assert "&lt;script&gt;" in html and "<script>bad" not in html
        from bs4 import BeautifulSoup
        document = BeautifulSoup(html, "html.parser")
        ids = [e["id"] for e in document.find_all(id=True)]
        assert len(ids) == len(set(ids))
        for form in document.find_all("form", method="post"):
            assert form.get("enctype", "application/x-www-form-urlencoded") == "application/x-www-form-urlencoded"
            assert form.find("input", attrs={"name": "csrf", "type": "hidden"})
        for i in range(20):
            client.post("/login", data={"csrf": "bad"})
        assert client.post("/login", data={"csrf": "bad"}).status_code == 429
    body = {"timezone": "UTC", "rows": [{"note": " =HYPERLINK(1)", "other": "\n@cmd"}]}
    text = csv_export(body)
    assert "' =HYPERLINK" in text and "'\n@cmd" in text


def test_retention_preview_apply_replay_and_backup_restore(app, tmp_path):
    store, pipeline, engine = app.state.store, app.state.pipeline, app.state.reliable
    store.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=0)
    frames = samples(app, utcnow() - timedelta(days=40), [True, True, True, False, False], step=10)
    assert store.evidence(SID, frames[0].frame_id)
    before = store.events()
    days = {"evidence": 30, "raw": 30, "audit": 365}
    future = utcnow() + timedelta(days=40)
    preview = engine.retention(days, now=future)
    assert preview["counts"]["evidence"] == 5 and store.evidence(SID, frames[0].frame_id)
    engine.retention(days, apply=True, now=future)
    assert store.evidence(SID, frames[0].frame_id) is None
    row = store.observations()[0]
    assert row["answer"]["raw_provider_fields"] is None
    obs = store.observation(row["id"])
    assert obs["run"]["provider_raw"] is None
    store.replay_all()
    assert store.events() == before
    bundle = configuration(engine.settings, store, engine)
    saved = backup(store, bundle, tmp_path / "backup")
    restored_path = restore(saved, tmp_path / "restored")
    restored_settings = load_config(restored_path)
    restored_store = Store(restored_settings.database)
    assert restored_store.events() == before
    assert restored_store.health()["observation_count"] == 15
    with pytest.raises(FileExistsError):
        restore(saved, tmp_path / "restored")
    with (saved / "vop.sqlite3").open("ab") as file:
        file.write(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        restore(saved, tmp_path / "bad-restore")
    assert not (tmp_path / "bad-restore").exists()


def test_configuration_round_trip_policies_rules_and_invalid_import(app, tmp_path):
    engine, store = app.state.reliable, app.state.store
    engine.save_rule(rule("count", threshold=2))
    record = store.questions(SID)[0]
    q = store.edit_question(SID, record["spec"], replace(record["policy"], positive_confirmations=3), enabled=False)
    store.set_mock_value(SID, QID, q.version, False)
    package = configuration(engine.settings, store, engine)
    path = tmp_path / "export.json"
    path.write_text(dumps(package), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("vop_release_tool", ROOT / "tools/release.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    destination = mod.import_configuration(path, tmp_path / "imported")
    imported = Store(load_config(destination).database)
    assert imported.questions(SID)[0]["policy"].positive_confirmations == 3
    assert imported.questions(SID)[0]["enabled"] is False
    package["config"]["database"] = "../../unsafe.sqlite3"
    path.write_text(dumps(package), encoding="utf-8")
    with pytest.raises(ValueError):
        mod.import_configuration(path, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_webhook_rejects_unapproved_urls_without_network(app, monkeypatch):
    reliable = app.state.reliable
    monkeypatch.setenv("VOP_WEBHOOK_ALLOWED_HOSTS", "approved.invalid")
    for endpoint in ("http://approved.invalid", "https://denied.invalid", "https://user:password@approved.invalid", "https://approved.invalid/#fragment", "https://127.0.0.1"):
        monkeypatch.setenv("VOP_WEBHOOK_URL", endpoint)
        assert reliable.send_webhook({}, "id") == "permanent_failure"


def test_health_alerts_are_distinct_and_stopped_sources_do_not_alert(app):
    store, engine, pipeline = app.state.store, app.state.reliable, app.state.pipeline
    engine.save_rule(rule("source_offline", id="offline"))
    engine.save_rule(rule("processing_degraded", id="degraded"))
    pipeline.record_gap(SID)
    engine.evaluate()
    assert not engine.alerts()  # no offline claim for stopped sampling
    store.update_source(SID, enabled=True, retain_evidence=False, sample_interval_seconds=1)
    engine.evaluate()
    assert [a["kind"] for a in engine.alerts()] == ["source_offline"]
    # A captured image with invalid model output is a processing error, not a failed capture.
    pipeline.engine.configure_source_answer(SID, QID, "1", None)
    pipeline.run(SID)
    engine.evaluate()
    assert {a["kind"] for a in engine.alerts()} == {"source_offline", "processing_degraded"}


def test_sender_http_status_key_and_credentials_never_exported(app, monkeypatch):
    from urllib.error import HTTPError
    import vop.reliable as module
    monkeypatch.setenv("VOP_WEBHOOK_URL", "https://approved.invalid/hook")
    monkeypatch.setenv("VOP_WEBHOOK_ALLOWED_HOSTS", "approved.invalid")
    monkeypatch.setenv("VOP_WEBHOOK_TOKEN", "offline-fake-secret")
    class Sink:
        def open(self, request, timeout):
            assert request.get_header("Idempotency-key") == "stable-key"
            assert request.get_header("Authorization") == "Bearer offline-fake-secret"
            assert timeout == 5
            raise HTTPError(request.full_url, 503, "Temporary", {}, None)
    monkeypatch.setattr(module, "build_opener", lambda *args: Sink())
    assert app.state.reliable.send_webhook({"synthetic": True}, "stable-key") == "temporary_failure"
    package = configuration(app.state.reliable.settings, app.state.store, app.state.reliable)
    assert "offline-fake-secret" not in dumps(package) and "approved.invalid" not in dumps(package)


def test_v2_migration_backup_and_v3_data_survive(app, tmp_path):
    from vop.storage import SCHEMA, MIGRATION_2
    path = tmp_path / "v2.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.executescript(MIGRATION_2)
        db.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), "legacy", "preserved"))
    store = Store(path)
    assert store.health()["database_schema"] == 3
    with sqlite3.connect(str(path) + ".v2-backup.sqlite3") as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
    with store.connection() as db:
        assert db.execute("SELECT outcome FROM audit WHERE action='legacy'").fetchone()[0] == "preserved"
