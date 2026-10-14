"""Durable rules, dashboard delivery, exports and explicit maintenance. No model imports."""
from dataclasses import asdict
from datetime import timedelta
import csv
from hashlib import sha256
from io import StringIO
import json
import math
import os
from pathlib import Path
import sqlite3
from threading import Event, Lock, Thread
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

from vop.config import ENV, identifier, load_config
from vop.contracts import utcnow
from vop.measurements import utc, timezone_for
from vop.storage import dumps
from vop.inputs.sources import NoRedirect

MIGRATION_3 = """
BEGIN IMMEDIATE;
CREATE TABLE rules(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, configuration TEXT NOT NULL);
CREATE TABLE rule_versions(id TEXT NOT NULL,revision INTEGER NOT NULL,configuration TEXT NOT NULL,PRIMARY KEY(id,revision));
CREATE TRIGGER immutable_rule_update BEFORE UPDATE ON rule_versions
 BEGIN SELECT RAISE(ABORT,'Rule revisions are immutable'); END;
CREATE TRIGGER immutable_rule_delete BEFORE DELETE ON rule_versions
 BEGIN SELECT RAISE(ABORT,'Rule revisions are immutable'); END;
CREATE TABLE rule_states(id TEXT PRIMARY KEY, active INTEGER NOT NULL, transition INTEGER NOT NULL);
CREATE TABLE alerts(id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, rule_revision INTEGER NOT NULL,
 created_at_utc TEXT NOT NULL, kind TEXT NOT NULL, severity TEXT NOT NULL, source_id TEXT NOT NULL,
 question_id TEXT NOT NULL, question_version TEXT NOT NULL, event_id TEXT,
 status TEXT NOT NULL, note TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE TABLE deliveries(alert_id TEXT NOT NULL REFERENCES alerts(id), channel TEXT NOT NULL,
 status TEXT NOT NULL, attempts INTEGER NOT NULL, next_attempt_utc TEXT NOT NULL,
 PRIMARY KEY(alert_id,channel));
CREATE TABLE release_settings(id TEXT PRIMARY KEY, value_json TEXT NOT NULL);
PRAGMA user_version=3;
COMMIT;
"""

RULE_FIELDS = {"id", "source_id", "question_id", "kind", "threshold", "window_seconds", "severity", "enabled", "webhook"}


def validate_rule(body, store, source_ids):
    if not isinstance(body, dict) or set(body) - RULE_FIELDS:
        raise ValueError("Unknown rule fields")
    result = dict(body)
    for key in ("id", "source_id", "question_id"):
        identifier(result.get(key))
    if result["source_id"] not in source_ids:
        raise ValueError("Unknown source")
    questions = {r["spec"].question_id: r["spec"] for r in store.questions(result["source_id"])}
    if result["question_id"] not in questions:
        raise ValueError("Unknown question")
    if result.get("kind") not in ("duration", "count", "source_offline", "processing_degraded"):
        raise ValueError("Unknown rule kind")
    if result["kind"] in ("duration", "count") and questions[result["question_id"]].kind != "binary":
        raise ValueError("Detection rules require a binary question")
    for key, default, low, high in (("threshold", 3600, 0, 31536000), ("window_seconds", 3600, 1, 31536000)):
        value = result.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError("Invalid rule threshold/window")
        result[key] = value
    if result["kind"] == "count" and int(result["threshold"]) != result["threshold"]:
        raise ValueError("Count threshold must be an integer")
    result.setdefault("severity", "warning")
    if result["severity"] not in ("info", "warning", "critical"):
        raise ValueError("Invalid severity")
    for key, default in (("enabled", True), ("webhook", False)):
        result.setdefault(key, default)
        if type(result[key]) is not bool:
            raise ValueError("Rule controls must be boolean")
    return result


class Reliable:
    def __init__(self, store, settings, pipeline, *, sender=None):
        self.store, self.settings, self.pipeline = store, settings, pipeline
        self.sender = sender or self.send_webhook
        self.lock, self.stop_event = Lock(), Event()
        self.thread = None
        self.last_error = None

    def rules(self):
        with self.store.connection() as db:
            return [{**json.loads(r["configuration"]), "revision": r["revision"]} for r in db.execute("SELECT * FROM rules ORDER BY id")]

    def save_rule(self, body):
        body = validate_rule(body, self.store, tuple(self.pipeline.sources))
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM rules WHERE id=?", (body["id"],)).fetchone()
            revision = row[0] + 1 if row else 1
            db.execute("INSERT OR REPLACE INTO rules VALUES(?,?,?)", (body["id"], revision, dumps(body)))
            db.execute("INSERT INTO rule_versions VALUES(?,?,?)", (body["id"], revision, dumps(body)))
            # A revision is an explicit new rule, never a reinterpretation of old alerts.
            db.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), "rule_edit", dumps({"id": body["id"], "revision": revision})))
        return revision

    def alerts(self, *, source_id=None, severity=None, question_id=None, start=None, end=None):
        if severity and severity not in ("info", "warning", "critical"):
            raise ValueError("Invalid severity")
        a, b = utc(start).isoformat() if start else None, utc(end).isoformat() if end else None
        with self.store.connection() as db:
            rows = db.execute("SELECT * FROM alerts WHERE (? IS NULL OR source_id=?) AND (? IS NULL OR severity=?) AND (? IS NULL OR question_id=?) AND (? IS NULL OR created_at_utc>=?) AND (? IS NULL OR created_at_utc<?) ORDER BY created_at_utc DESC LIMIT 1000", (source_id, source_id, severity, severity, question_id, question_id, a, a, b, b)).fetchall()
            return [{**dict(r), "payload": json.loads(r["payload_json"]), "deliveries": [dict(d) for d in db.execute("SELECT channel,status,attempts,next_attempt_utc FROM deliveries WHERE alert_id=?", (r["id"],))]} for r in rows]

    def update_alert(self, alert_id, action, note):
        if action not in ("acknowledged", "resolved", "note") or not isinstance(note, str) or len(note) > 4096:
            raise ValueError("Invalid acknowledgement or note")
        with self.store.connection() as db:
            row = db.execute("SELECT status FROM alerts WHERE id=?", (alert_id,)).fetchone()
            if not row:
                raise ValueError("Unknown alert")
            if row[0] == "resolved" and action == "acknowledged":
                raise ValueError("A resolved alert cannot be acknowledged again")
            db.execute("UPDATE alerts SET status=?,note=? WHERE id=?", (row[0] if action == "note" else action, note, alert_id))
            db.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), "alert_" + action, dumps({"id": alert_id, "actor": "operator", "note": note})))

    def evaluate(self, now=None):
        now = utc(now) if now else utcnow()
        for rule in self.rules():
            sid, qid = rule["source_id"], rule["question_id"]
            question = next(r for r in self.store.questions(sid) if r["spec"].question_id == qid)
            q = question["spec"]
            summary = self.store.summary(sid, qid, q.version, kind=q.kind, as_of=now)
            source = self.store.source_control(sid)
            kind = rule["kind"]
            eligible = rule["enabled"] and question["enabled"] and source["enabled"]
            event = next((e for e in reversed(summary["events"]) if e["status"] == "open"), None)
            if kind == "duration":
                active = eligible and summary["state"] == "ACTIVE" and event is not None and event["estimated_observed_seconds"] > rule["threshold"]
                discriminator = event["id"] if event else "none"
            elif kind == "count":
                counted_events = [e for e in summary["events"] if now - timedelta(seconds=rule["window_seconds"]) <= utc(e["started_at_utc"]) <= now]
                count = len(counted_events)
                active = eligible and summary["state"] != "UNKNOWN" and count > rule["threshold"]
                discriminator = "window"
            elif kind == "source_offline":
                source_row = next(s for s in self.store.sources(tuple(self.pipeline.sources)) if s["source_id"] == sid)
                active = eligible and source["sample_interval_seconds"] > 0 and (summary["stale"] or source_row["status"] == "DISCONNECTED")
                discriminator = "health"
            else:
                latest = self.store.observation(summary["last_observation_id"]) if summary["last_observation_id"] else None
                active = eligible and latest is not None and latest["status"] != "success" and latest["run"]["frame_id"] is not None
                discriminator = "health"
            state_key = f"{rule['id']}:{rule['revision']}:{q.version}:{discriminator}"
            observation_ids = [e["start_observation_id"] for e in counted_events] if kind == "count" else [summary["last_observation_id"]]
            recorded_runs = [r["run"] for oid in observation_ids if oid and (r := self.store.observation(oid))]
            provenance = sorted({(r["engine_id"], r["engine_version"], r["synthetic"]) for r in recorded_runs})
            with self.store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                previous = db.execute("SELECT active,transition FROM rule_states WHERE id=?", (state_key,)).fetchone()
                # UNKNOWN suspends a detection rule; it never creates a safe transition/re-arm.
                if kind in ("duration", "count") and eligible and summary["state"] == "UNKNOWN":
                    continue
                transition = previous[1] if previous else 0
                if active and (not previous or not previous[0]):
                    transition += 1
                    # Duration is delivered at most once per episode, even after unknown/resume.
                    key = f"{state_key}:{1 if kind == 'duration' else transition}"
                    alert_id = sha256(key.encode()).hexdigest()[:32]
                    payload = {"id": alert_id, "rule_id": rule["id"], "rule_revision": rule["revision"], "kind": kind,
                               "severity": rule["severity"], "source_id": sid, "question_id": qid, "question_version": q.version,
                               "created_at_utc": now.isoformat(), "event_id": event["id"] if event and kind == "duration" else None,
                               "synthetic": any(synthetic for eid, ver, synthetic in provenance),
                               "engine_id": provenance[0][0] if len(provenance) == 1 else "mixed",
                               "provenance": [{"engine_id": eid, "engine_version": ver, "synthetic": synthetic} for eid, ver, synthetic in provenance],
                               "rule": rule,
                               "measurement": "bounded sampled intervals" if kind == "duration" else kind}
                    inserted = db.execute("INSERT OR IGNORE INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                         (alert_id, rule["id"], rule["revision"], now.isoformat(), kind, rule["severity"], sid, qid, q.version, payload["event_id"], "open", "", dumps(payload))).rowcount
                    if inserted:
                        db.execute("INSERT INTO deliveries VALUES(?,?,?,?,?)", (alert_id, "dashboard", "delivered", 1, now.isoformat()))
                        if rule["webhook"]:
                            db.execute("INSERT INTO deliveries VALUES(?,?,?,?,?)", (alert_id, "webhook", "pending", 0, now.isoformat()))
                        db.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (now.isoformat(), "alert_created", alert_id))
                db.execute("INSERT OR REPLACE INTO rule_states VALUES(?,?,?)", (state_key, int(active), transition))

    def retry(self, now=None):
        now = utc(now) if now else utcnow()
        # One worker claims before sending. A crash leaves 'sending'; next process retries using the same key.
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT d.*,a.payload_json FROM deliveries d JOIN alerts a ON a.id=d.alert_id WHERE d.channel='webhook' AND d.status IN ('pending','retry') AND d.next_attempt_utc<=? ORDER BY d.next_attempt_utc LIMIT 1", (now.isoformat(),)).fetchone()
            if not row:
                return
            db.execute("UPDATE deliveries SET status='sending',attempts=attempts+1 WHERE alert_id=? AND channel='webhook'", (row["alert_id"],))
        try:
            outcome = self.sender(json.loads(row["payload_json"]), row["alert_id"])
            if outcome not in ("delivered", "temporary_failure", "permanent_failure"):
                outcome = "permanent_failure"
        except Exception:
            outcome = "temporary_failure"
        attempts = row["attempts"] + 1
        status = "delivered" if outcome == "delivered" else "failed" if outcome == "permanent_failure" or attempts >= 5 else "retry"
        with self.store.connection() as db:
            db.execute("UPDATE deliveries SET status=?,next_attempt_utc=? WHERE alert_id=? AND channel='webhook'", (status, (now + timedelta(seconds=min(300, 2 ** attempts))).isoformat(), row["alert_id"]))
            db.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (now.isoformat(), "alert_delivery", dumps({"id": row["alert_id"], "status": status, "attempt": attempts})))

    def send_webhook(self, payload, key):
        # Explicit OS environment configuration; no endpoint or credentials in database/UI/exports.
        endpoint = os.environ.get("VOP_WEBHOOK_URL", "")
        allowed = os.environ.get("VOP_WEBHOOK_ALLOWED_HOSTS", "").split(",")
        parsed = urlsplit(endpoint)
        if parsed.scheme != "https" or not parsed.hostname or parsed.hostname not in allowed or parsed.username is not None or parsed.password is not None or parsed.fragment:
            return "permanent_failure"
        parsed.port
        from urllib.error import HTTPError
        headers = {"Content-Type": "application/json", "Idempotency-Key": key}
        secret = os.environ.get("VOP_WEBHOOK_TOKEN", "")
        if secret:
            headers["Authorization"] = "Bearer " + secret
        try:
            with build_opener(NoRedirect(), ProxyHandler({})).open(Request(endpoint, data=dumps(payload).encode(), headers=headers), timeout=5) as response:
                return "delivered" if 200 <= response.status < 300 else "permanent_failure"
        except HTTPError as exc:
            return "temporary_failure" if exc.code == 429 or exc.code >= 500 else "permanent_failure"
        except Exception as exc:
            from vop.contracts import ProviderError
            return "permanent_failure" if isinstance(exc, ProviderError) else "temporary_failure"

    def tick(self, now=None):
        if not self.lock.acquire(False):
            return
        try:
            self.evaluate(now)
            self.retry(now)
            self.last_error = None
        finally:
            self.lock.release()

    def start(self):
        with self.store.connection() as db:
            db.execute("UPDATE deliveries SET status=CASE WHEN attempts>=5 THEN 'failed' ELSE 'retry' END WHERE status='sending'")
        self.stop_event.clear()
        self.thread = Thread(target=self.loop, name="vop-alerts", daemon=True)
        self.thread.start()

    def loop(self):
        from time import monotonic
        retention_due = monotonic() + 3600
        while not self.stop_event.is_set():
            try:
                self.tick()
                if monotonic() >= retention_due:
                    with self.store.connection() as db:
                        row = db.execute("SELECT value_json FROM release_settings WHERE id='retention'").fetchone()
                    if row:
                        self.retention(json.loads(row[0]), apply=True)
                    retention_due = monotonic() + 3600
            except Exception:
                self.last_error = "rule_processing_failed"
            self.stop_event.wait(1)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=6)

    def export(self, kind, *, zone="UTC", source_id=None, question_id=None, start=None, end=None, severity=None):
        timezone_for(zone)
        if source_id and source_id not in self.pipeline.sources:
            raise ValueError("Unknown source")
        if kind == "alerts":
            rows = self.alerts(source_id=source_id, question_id=question_id, start=start, end=end, severity=severity)
            rows = [{k: v for k, v in r.items() if k != "payload_json"} for r in rows]
        elif kind == "events":
            with self.store.connection() as db:
                rows = [json.loads(r[0]) for r in db.execute("SELECT event_json FROM events ORDER BY started_at_utc")]
            rows = [r for r in rows if (not source_id or r["source_id"] == source_id) and (not question_id or r["question_id"] == question_id) and (not start or utc(r["started_at_utc"]) >= utc(start)) and (not end or utc(r["started_at_utc"]) < utc(end))]
            for row in rows:
                obs = self.store.observation(row["start_observation_id"])
                if obs:
                    row["provenance"] = {k: obs["run"][k] for k in ("engine_id", "engine_version", "synthetic")}
        elif kind == "metrics":
            rows = []
            for sid in self.pipeline.sources:
                if source_id and source_id != sid:
                    continue
                for record in self.store.questions(sid):
                    q = record["spec"]
                    if question_id and q.question_id != question_id:
                        continue
                    with self.store.connection() as db:
                        provenance = [json.loads(r[0]) for r in db.execute("SELECT DISTINCT r.result_json FROM runs r JOIN observations o ON o.run_id=r.id WHERE o.source_id=? AND o.question_id=? AND o.question_version=?", (sid, q.question_id, q.version))]
                    engines = sorted({(r["engine_id"], r["engine_version"], r["synthetic"]) for r in provenance})
                    rows.append({"source_id": sid, "question_id": q.question_id, "question_version": q.version,
                                 "provenance": [{"engine_id": eid, "engine_version": ver, "synthetic": synthetic} for eid, ver, synthetic in engines],
                                 "summary": self.store.summary(sid, q.question_id, q.version, kind=q.kind, as_of=utcnow(), timezone_name=zone, range_start=start, range_end=end)})
        else:
            raise ValueError("Unknown export kind")
        self.store.audit("export", dumps({"kind": kind, "rows": len(rows)}))
        return {"schema_version": 1, "timezone": zone, "kind": kind, "rows": rows}

    def retention(self, days, *, apply=False, now=None):
        # Keep minimal normalized history for deterministic replay. Strip raw provider detail, not measured values.
        if not isinstance(days, dict) or set(days) != {"evidence", "raw", "audit"} or any(type(d) is not int or not 1 <= d <= 36500 for d in days.values()):
            raise ValueError("Retention windows require integer days (1–36500)")
        now = utc(now) if now else utcnow()
        cutoffs = {k: (now - timedelta(days=v)).isoformat() for k, v in days.items()}
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            counts = {"evidence": db.execute("SELECT count(*) FROM frames WHERE captured_at_utc<? AND evidence_png IS NOT NULL", (cutoffs["evidence"],)).fetchone()[0],
                      "raw": db.execute("SELECT count(*) FROM runs WHERE processed_at_utc<? AND result_json NOT LIKE '%\"raw_retained\": false%'", (cutoffs["raw"],)).fetchone()[0],
                      "audit": db.execute("SELECT count(*) FROM audit WHERE created_at_utc<?", (cutoffs["audit"],)).fetchone()[0]}
            if apply:
                db.execute("UPDATE frames SET evidence_png=NULL WHERE captured_at_utc<?", (cutoffs["evidence"],))
                for row in db.execute("SELECT id,result_json FROM runs WHERE processed_at_utc<?", (cutoffs["raw"],)).fetchall():
                    body = json.loads(row["result_json"])
                    body["raw_retained"] = False
                    body["provider_raw"] = None
                    body["usage"] = None
                    for answer in body["answers"]:
                        answer["raw_provider_fields"] = None
                        answer["usage"] = None
                    db.execute("UPDATE runs SET result_json=? WHERE id=?", (dumps(body), row["id"]))
                    for answer in db.execute("SELECT id,answer_json FROM observations WHERE run_id=?", (row["id"],)).fetchall():
                        data = json.loads(answer["answer_json"])
                        data["raw_provider_fields"] = None
                        data["usage"] = None
                        db.execute("UPDATE observations SET answer_json=? WHERE id=?", (dumps(data), answer["id"]))
                db.execute("DELETE FROM audit WHERE created_at_utc<?", (cutoffs["audit"],))
                db.execute("INSERT OR REPLACE INTO release_settings VALUES('retention',?)", (dumps(days),))
                db.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (now.isoformat(), "retention", dumps(counts)))
        if apply:
            self.pipeline.latest_preview = None
            with self.store.connection() as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"cutoffs": cutoffs, "counts": counts, "applied": apply, "normalized_history": "retained for replay"}


def csv_export(body):
    rows = body["rows"]
    columns = sorted({k for row in rows for k in row} | {"timezone"})
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        values = {**row, "timezone": body["timezone"]}
        for k, v in values.items():
            value = dumps(v) if isinstance(v, (dict, list)) else "" if v is None else str(v)
            # CSV formula injection protection, including whitespace/control prefixes.
            values[k] = "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")) else value
        writer.writerow(values)
    return output.getvalue()


def configuration(settings, store, reliable):
    sources = []
    policies = []
    for source in reliable.pipeline.sources.values():
        questions = []
        for record in store.questions(source.source_id):
            q = record["spec"]
            spec = asdict(q)
            spec["id"] = spec.pop("question_id")
            questions.append(spec)
            policies.append({"source_id": source.source_id, "question_id": q.question_id, "version": q.version, "enabled": record["enabled"], "policy": asdict(record["policy"])})
        sources.append({"id": source.source_id, "name": source.name, "kind": source.kind, "settings": source.settings,
                        "questions": questions, **store.source_control(source.source_id)})
    return {"schema_version": 1, "config": {"schema_version": 1, "database": "data/vop.sqlite3", "timezone": settings.timezone_name,
             "engine": getattr(reliable.pipeline, "engine_profile", None) or settings.engine or {"kind": "mock", "id": settings.engine_id, "answers": settings.mock_answers}, "sources": sources,
             "capture_timeout_seconds": settings.capture_timeout_seconds, "inference_timeout_seconds": settings.inference_timeout_seconds},
            "policies": policies, "mock_values": [r for r in store.mock_values() if r[:3] in {(p['source_id'], p['question_id'], p['version']) for p in policies}], "rules": [{k: v for k, v in r.items() if k != "revision"} for r in reliable.rules()]}


def backup(store, config, destination):
    """SQLite's backup includes WAL and evidence; manifest authenticates accidental corruption, not trust."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    try:
        with store.connection() as source, sqlite3.connect(destination / "vop.sqlite3") as target:
            source.backup(target)
        (destination / "configuration.json").write_text(dumps(config), encoding="utf-8")
        manifest = {"schema_version": 1, "database_schema": 3, "files": {name: sha256((destination / name).read_bytes()).hexdigest() for name in ("vop.sqlite3", "configuration.json")}}
        (destination / "manifest.json").write_text(dumps(manifest), encoding="utf-8")
        store.audit("backup", "created")
    except Exception:
        # Leave failed backup available for diagnosis; never label it complete.
        raise
    return destination


def restore(source, destination):
    """Offline restore into a new directory, never overwrite a running database."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("database_schema") != 3 or set(manifest.get("files", {})) != {"vop.sqlite3", "configuration.json"}:
        raise ValueError("Unsupported backup manifest")
    for name, digest in manifest["files"].items():
        if sha256((source / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Backup checksum mismatch")
    with sqlite3.connect(f"file:{(source / 'vop.sqlite3').as_posix()}?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchone() or db.execute("PRAGMA user_version").fetchone()[0] != 3:
            raise ValueError("Backup database validation failed")
    package = json.loads((source / "configuration.json").read_text(encoding="utf-8"))
    if package.get("schema_version") != 1 or package.get("config", {}).get("database") != "data/vop.sqlite3":
        raise ValueError("Unsupported configuration package")
    # Validate config before creating destination. Preserve operator-selected file references.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="vop-restore-validation-") as temp:
        check = Path(temp) / "config.json"
        check.write_text(dumps(package["config"]), encoding="utf-8")
        load_config(check)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "data").mkdir()
    with sqlite3.connect(source / "vop.sqlite3") as old, sqlite3.connect(destination / "data" / "vop.sqlite3") as new:
        old.backup(new)
    (destination / "config.json").write_text(dumps(package["config"]), encoding="utf-8")
    return destination / "config.json"
