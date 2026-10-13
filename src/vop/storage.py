"""Versioned SQLite foundation. No image pixels or secret values are stored."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from vop.config import Settings
from vop.contracts import json_default, utcnow
from vop.contracts import AnswerKind, QuestionSpec
from vop.measurements import QueryPolicy, replay, utc

SCHEMA = """
BEGIN IMMEDIATE;
CREATE TABLE sources (
 id TEXT PRIMARY KEY, configuration TEXT NOT NULL, status TEXT NOT NULL,
 last_frame_utc TEXT
);
CREATE TABLE question_versions (
 source_id TEXT NOT NULL REFERENCES sources(id), question_id TEXT NOT NULL,
 version TEXT NOT NULL, specification TEXT NOT NULL,
 PRIMARY KEY(source_id,question_id,version)
);
CREATE TRIGGER immutable_question_update BEFORE UPDATE ON question_versions
 BEGIN SELECT RAISE(ABORT, 'Question versions are immutable'); END;
CREATE TRIGGER immutable_question_delete BEFORE DELETE ON question_versions
 BEGIN SELECT RAISE(ABORT, 'Question versions are immutable'); END;
CREATE TABLE frames (
 source_id TEXT NOT NULL REFERENCES sources(id), frame_id TEXT NOT NULL,
 captured_at_utc TEXT NOT NULL, received_at_utc TEXT NOT NULL, sha256 TEXT NOT NULL,
 width INTEGER NOT NULL, height INTEGER NOT NULL, content_type TEXT NOT NULL,
 PRIMARY KEY(source_id,frame_id)
);
CREATE TABLE runs (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
 frame_id TEXT, processed_at_utc TEXT NOT NULL, result_json TEXT NOT NULL,
 FOREIGN KEY(source_id,frame_id) REFERENCES frames(source_id,frame_id)
);
CREATE UNIQUE INDEX one_run_per_frame ON runs(source_id,frame_id) WHERE frame_id IS NOT NULL;
CREATE TABLE observations (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(id), source_id TEXT NOT NULL,
 question_id TEXT NOT NULL, question_version TEXT NOT NULL,
 captured_at_utc TEXT, processed_at_utc TEXT NOT NULL,
 status TEXT NOT NULL, normalised_state TEXT NOT NULL, answer_json TEXT NOT NULL,
 FOREIGN KEY(source_id,question_id,question_version)
 REFERENCES question_versions(source_id,question_id,version),
 CHECK(status='success' OR normalised_state IN ('error','unknown'))
);
CREATE INDEX observations_source ON observations(source_id,sequence);
CREATE TABLE audit (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, created_at_utc TEXT NOT NULL,
 action TEXT NOT NULL, outcome TEXT NOT NULL
);
PRAGMA user_version=1;
COMMIT;
"""

MIGRATION_2 = """
BEGIN IMMEDIATE;
ALTER TABLE frames ADD COLUMN evidence_png BLOB;
ALTER TABLE observations ADD COLUMN temporal_eligible INTEGER NOT NULL DEFAULT 1;
CREATE TABLE source_controls(source_id TEXT PRIMARY KEY REFERENCES sources(id), enabled INTEGER NOT NULL,
 evidence_enabled INTEGER NOT NULL, sample_interval_seconds REAL NOT NULL);
CREATE TABLE query_controls(source_id TEXT NOT NULL,question_id TEXT NOT NULL,current_version TEXT NOT NULL,
 enabled INTEGER NOT NULL,PRIMARY KEY(source_id,question_id));
CREATE TABLE query_policies(source_id TEXT NOT NULL,question_id TEXT NOT NULL,version TEXT NOT NULL,
 policy_json TEXT NOT NULL,PRIMARY KEY(source_id,question_id,version),
 FOREIGN KEY(source_id,question_id,version) REFERENCES question_versions(source_id,question_id,version));
CREATE TRIGGER immutable_policy_update BEFORE UPDATE ON query_policies
 BEGIN SELECT RAISE(ABORT,'Query policies are immutable'); END;
CREATE TABLE events(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,question_id TEXT NOT NULL,question_version TEXT NOT NULL,
 started_at_utc TEXT NOT NULL,event_json TEXT NOT NULL);
CREATE INDEX events_source ON events(source_id,started_at_utc);
CREATE TABLE mock_values(source_id TEXT NOT NULL,question_id TEXT NOT NULL,version TEXT NOT NULL,value_json TEXT NOT NULL,
 PRIMARY KEY(source_id,question_id,version));
PRAGMA user_version=2;
COMMIT;
"""


def dumps(value) -> str:
    return json.dumps(value, default=json_default, allow_nan=False, sort_keys=True)


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 2:
                raise ValueError("Database schema is newer than this application; restore/use compatible software")
            if version == 0:
                if connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone():
                    raise ValueError("Refusing to adopt an unversioned nonempty database")
                connection.executescript(SCHEMA)
            if version <= 1:
                # Keep a consistent pre-migration backup; never overwrite a previous backup.
                backup_path = self.path.with_name(self.path.name + ".v1-backup.sqlite3")
                if version == 1 and not backup_path.exists():
                    with sqlite3.connect(backup_path) as backup:
                        connection.backup(backup)
                connection.executescript(MIGRATION_2)
            connection.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA secure_delete=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def configure(self, settings: Settings) -> None:
        with self.connection() as connection:
            for source in settings.sources:
                configuration = dumps(source.public())
                existing = connection.execute("SELECT configuration FROM sources WHERE id=?", (source.source_id,)).fetchone()
                if existing:
                    old = json.loads(existing[0])
                    if old.get("enabled") != source.enabled:
                        connection.execute("UPDATE source_controls SET enabled=? WHERE source_id=?", (source.enabled, source.source_id))
                    connection.execute("UPDATE sources SET configuration=?,status=CASE WHEN ?=0 THEN 'DISABLED' WHEN status='DISABLED' THEN 'CONNECTING' ELSE status END WHERE id=?",
                                       (configuration, source.enabled, source.source_id))
                else:
                    connection.execute("INSERT INTO sources VALUES(?,?,?,NULL)",
                                       (source.source_id, configuration, "CONNECTING" if source.enabled else "DISABLED"))
                connection.execute("INSERT OR IGNORE INTO source_controls VALUES(?,?,?,?)",
                                   (source.source_id, source.enabled, source.retain_evidence, source.sample_interval_seconds))
                for question in source.questions:
                    spec = dumps(asdict(question))
                    key = (source.source_id, question.question_id, question.version)
                    saved = connection.execute("SELECT specification FROM question_versions WHERE source_id=? AND question_id=? AND version=?", key).fetchone()
                    if saved and saved[0] != spec:
                        raise ValueError("Question version already exists with different content; increment version")
                    if not saved:
                        connection.execute("INSERT INTO question_versions VALUES(?,?,?,?)", (*key, spec))
                        connection.execute("UPDATE query_controls SET current_version=? WHERE source_id=? AND question_id=?", (question.version, source.source_id, question.question_id))
                    connection.execute("INSERT OR IGNORE INTO query_controls VALUES(?,?,?,1)", key)
                    connection.execute("INSERT OR IGNORE INTO query_policies VALUES(?,?,?,?)", (*key, dumps(asdict(QueryPolicy()))))

    def audit(self, action: str, outcome: str) -> None:
        with self.connection() as connection:
            connection.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), action, outcome))

    def sources(self, source_ids: tuple[str, ...]) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM sources").fetchall()
        return [{**json.loads(r["configuration"]), **self.source_control(r["id"]), "status": r["status"] if self.source_control(r["id"])["enabled"] else "DISABLED", "last_frame_utc": r["last_frame_utc"],
                 "questions": [q["spec"].question_id for q in self.questions(r["id"])]}
                for r in rows if r["id"] in source_ids]

    def source_control(self, source_id: str) -> dict:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM source_controls WHERE source_id=?", (source_id,)).fetchone()
        if not row:
            raise ValueError("Unknown source")
        return {"enabled": bool(row["enabled"]), "retain_evidence": bool(row["evidence_enabled"]),
                "sample_interval_seconds": row["sample_interval_seconds"]}

    def update_source(self, source_id: str, *, enabled: bool, retain_evidence: bool, sample_interval_seconds: float):
        if type(enabled) is not bool or type(retain_evidence) is not bool or isinstance(sample_interval_seconds, bool) or not (sample_interval_seconds == 0 or 1 <= sample_interval_seconds <= 3600):
            raise ValueError("Invalid source controls")
        with self.connection() as connection:
            if not connection.execute("SELECT 1 FROM sources WHERE id=?", (source_id,)).fetchone():
                raise ValueError("Unknown source")
            connection.execute("UPDATE source_controls SET enabled=?,evidence_enabled=?,sample_interval_seconds=? WHERE source_id=?",
                               (enabled, retain_evidence, sample_interval_seconds, source_id))
            connection.execute("UPDATE sources SET status=CASE WHEN ?=0 THEN 'DISABLED' WHEN status='DISABLED' THEN 'CONNECTING' ELSE status END WHERE id=?", (enabled, source_id))
            connection.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), "source_controls", "updated"))

    def questions(self, source_id: str, *, active_only: bool = False) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute("SELECT v.specification,c.enabled,p.policy_json FROM query_controls c JOIN question_versions v ON v.source_id=c.source_id AND v.question_id=c.question_id AND v.version=c.current_version JOIN query_policies p ON p.source_id=v.source_id AND p.question_id=v.question_id AND p.version=v.version WHERE c.source_id=? AND (?=0 OR c.enabled=1) ORDER BY c.rowid", (source_id, active_only)).fetchall()
        result = []
        for row in rows:
            body = json.loads(row["specification"])
            body["kind"] = AnswerKind(body["kind"])
            body["choices"] = tuple(tuple(v) for v in body.get("choices", []))
            body["levels"] = tuple(body.get("levels", []))
            result.append({"spec": QuestionSpec(**body), "enabled": bool(row["enabled"]), "policy": QueryPolicy(**json.loads(row["policy_json"]))})
        return result

    def edit_question(self, source_id: str, question: QuestionSpec, policy: QueryPolicy, *, enabled: bool = True,
                      expected_version: str | None = None) -> QuestionSpec:
        with self.connection() as connection:
            current = connection.execute("SELECT current_version FROM query_controls WHERE source_id=? AND question_id=?", (source_id, question.question_id)).fetchone()
            if current is None and connection.execute("SELECT count(*) FROM query_controls WHERE source_id=?", (source_id,)).fetchone()[0] >= 32:
                raise ValueError("A source may have at most 32 questions")
            if expected_version is not None and (current is None or current[0] != expected_version):
                raise ValueError("Question changed in another request; reload before editing")
            from dataclasses import replace
            versions = {r[0] for r in connection.execute("SELECT version FROM question_versions WHERE source_id=? AND question_id=?", (source_id, question.question_id))}
            next_number = 1
            while str(next_number) in versions:
                next_number += 1
            question = replace(question, version=str(next_number))
            key = (source_id, question.question_id, question.version)
            connection.execute("INSERT INTO question_versions VALUES(?,?,?,?)", (*key, dumps(asdict(question))))
            connection.execute("INSERT INTO query_policies VALUES(?,?,?,?)", (*key, dumps(asdict(policy))))
            connection.execute("INSERT INTO query_controls VALUES(?,?,?,?) ON CONFLICT(source_id,question_id) DO UPDATE SET current_version=excluded.current_version,enabled=excluded.enabled", (*key, enabled))
            connection.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), "question_version", "created"))
        if current:
            with self.connection() as connection:
                self._rebuild(connection, source_id, question.question_id, current[0])
        return question

    def policy(self, source_id: str, question_id: str, version: str) -> QueryPolicy:
        with self.connection() as connection:
            row = connection.execute("SELECT policy_json FROM query_policies WHERE source_id=? AND question_id=? AND version=?", (source_id, question_id, version)).fetchone()
        return QueryPolicy(**json.loads(row[0])) if row else QueryPolicy()

    def _history(self, connection, source_id: str, question_id: str, version: str) -> list[dict]:
        # ponytail: O(n) replay for the starter dataset; incremental snapshots when history volume warrants it.
        rows = connection.execute("SELECT * FROM observations WHERE source_id=? AND question_id=? AND question_version=? ORDER BY sequence", (source_id, question_id, version)).fetchall()
        return [{**dict(r), "answer": json.loads(r["answer_json"])} for r in rows]

    def _rebuild(self, connection, source_id: str, question_id: str, version: str) -> dict:
        spec = connection.execute("SELECT specification FROM question_versions WHERE source_id=? AND question_id=? AND version=?", (source_id, question_id, version)).fetchone()
        policy = connection.execute("SELECT policy_json FROM query_policies WHERE source_id=? AND question_id=? AND version=?", (source_id, question_id, version)).fetchone()
        summary = replay(self._history(connection, source_id, question_id, version), QueryPolicy(**json.loads(policy[0])) if policy else QueryPolicy(), kind=json.loads(spec[0])["kind"])
        connection.execute("DELETE FROM events WHERE source_id=? AND question_id=? AND question_version=?", (source_id, question_id, version))
        current = connection.execute("SELECT current_version FROM query_controls WHERE source_id=? AND question_id=?", (source_id, question_id)).fetchone()
        if current and current[0] != version:
            for event in summary["events"]:
                if event["status"] == "open":
                    event.update(status="superseded", superseded_by_version=current[0])
        for event in summary["events"]:
            connection.execute("INSERT INTO events VALUES(?,?,?,?,?,?)", (event["id"], source_id, question_id, version, event["started_at_utc"], dumps(event)))
        return summary

    def replay_all(self):
        with self.connection() as connection:
            for row in connection.execute("SELECT source_id,question_id,version FROM question_versions").fetchall():
                self._rebuild(connection, *row)

    def summary(self, source_id: str, question_id: str, version: str, *, kind: str = "binary", as_of=None, timezone_name="UTC", range_start=None, range_end=None) -> dict:
        with self.connection() as connection:
            policy = connection.execute("SELECT policy_json FROM query_policies WHERE source_id=? AND question_id=? AND version=?", (source_id, question_id, version)).fetchone()
            history = self._history(connection, source_id, question_id, version)
            control = connection.execute("SELECT enabled,current_version FROM query_controls WHERE source_id=? AND question_id=?", (source_id, question_id)).fetchone()
            source = connection.execute("SELECT enabled FROM source_controls WHERE source_id=?", (source_id,)).fetchone()
        result = replay(history, QueryPolicy(**json.loads(policy[0])) if policy else QueryPolicy(), kind=kind, as_of=as_of, timezone_name=timezone_name, range_start=range_start, range_end=range_end)
        if source and not source[0] or control and (not control[0] or control[1] != version):
            result.update(state="UNKNOWN", latest_value=None, disabled=True)
        return result

    def events(self, source_id: str | None = None, *, limit: int = 100) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute("SELECT event_json FROM events WHERE (? IS NULL OR source_id=?) ORDER BY started_at_utc DESC LIMIT ?", (source_id, source_id, limit)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def event_count(self, source_id: str | None = None) -> int:
        with self.connection() as connection:
            return connection.execute("SELECT count(*) FROM events WHERE (? IS NULL OR source_id=?)", (source_id, source_id)).fetchone()[0]

    def evidence(self, source_id: str, frame_id: str) -> bytes | None:
        with self.connection() as connection:
            row = connection.execute("SELECT evidence_png FROM frames WHERE source_id=? AND frame_id=?", (source_id, frame_id)).fetchone()
        return bytes(row[0]) if row and row[0] is not None else None

    def delete_evidence(self, source_id: str, frame_id: str):
        with self.connection() as connection:
            connection.execute("UPDATE frames SET evidence_png=NULL WHERE source_id=? AND frame_id=?", (source_id, frame_id))
            connection.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), "evidence", "deleted"))
        with self.connection() as connection:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def observation(self, observation_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT o.*,r.result_json FROM observations o JOIN runs r ON o.run_id=r.id WHERE o.id=?", (observation_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["answer"] = json.loads(item.pop("answer_json"))
        item["run"] = json.loads(item.pop("result_json"))
        return item

    def set_mock_value(self, source_id, question_id, version, value):
        with self.connection() as connection:
            connection.execute("INSERT OR REPLACE INTO mock_values VALUES(?,?,?,?)", (source_id, question_id, version, dumps(value)))

    def mock_values(self):
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM mock_values").fetchall()
        return [(r["source_id"], r["question_id"], r["version"], json.loads(r["value_json"])) for r in rows]

    def previous(self, source_id: str, frame_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT r.id,r.result_json,f.sha256 FROM runs r JOIN frames f USING(source_id,frame_id) WHERE r.source_id=? AND r.frame_id=?", (source_id, frame_id)).fetchone()
        return {"run_id": row["id"], "result": json.loads(row["result_json"]), "sha256": row["sha256"]} if row else None

    def save(self, source_id: str, frame, result: dict, evidence_png: bytes | None = None) -> dict:
        run_id = str(uuid4())
        processed = result["processed_at_utc"]
        with self.connection() as connection:
            if frame:
                connection.execute("INSERT INTO frames VALUES(?,?,?,?,?,?,?,?,?)", (source_id, frame.frame_id,
                                   frame.captured_at_utc.isoformat(), frame.received_at_utc.isoformat(), frame.sha256,
                                   frame.width, frame.height, frame.content_type, evidence_png))
            connection.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (run_id, source_id, result["frame_id"], processed, dumps(result)))
            for answer in result["answers"]:
                value = answer["value"]
                state = ("positive" if value is True else "negative" if value is False else "not_applicable") if answer["status"] == "success" else "error"
                connection.execute("INSERT INTO observations(id,run_id,source_id,question_id,question_version,captured_at_utc,processed_at_utc,status,normalised_state,answer_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   (str(uuid4()), run_id, source_id, answer["question_id"], answer["question_version"],
                                    result["captured_at_utc"], processed, answer["status"], state, dumps(answer)))
                row_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
                previous_stamp = connection.execute("SELECT captured_at_utc,processed_at_utc FROM observations WHERE source_id=? AND question_id=? AND question_version=? AND sequence<? AND temporal_eligible=1 ORDER BY sequence DESC LIMIT 1",
                                                    (source_id, answer["question_id"], answer["question_version"], row_id)).fetchone()
                stamp = result["captured_at_utc"] or processed
                source_enabled = connection.execute("SELECT enabled FROM source_controls WHERE source_id=?", (source_id,)).fetchone()[0]
                if frame is not None and not source_enabled or previous_stamp and utc(stamp) < utc(previous_stamp[0] or previous_stamp[1]):
                    connection.execute("UPDATE observations SET temporal_eligible=0 WHERE sequence=?", (row_id,))
                    connection.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (processed, "late_observation", "excluded_from_live_state"))
                self._rebuild(connection, source_id, answer["question_id"], answer["question_version"])
            connection.execute("UPDATE sources SET status=?,last_frame_utc=COALESCE(?,last_frame_utc) WHERE id=?",
                               ("HEALTHY" if frame else "DISCONNECTED", result["captured_at_utc"], source_id))
            connection.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (processed, "capture_inference", result["status"]))
        return {"run_id": run_id, "result": result, "duplicate": False}

    def observations(self, source_id: str | None = None, *, after: int = 0, limit: int = 20) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute("SELECT o.*,r.result_json FROM observations o JOIN runs r ON r.id=o.run_id WHERE o.sequence>? AND (? IS NULL OR o.source_id=?) ORDER BY o.sequence LIMIT ?",
                                      (after, source_id, source_id, limit)).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            answer = json.loads(item.pop("answer_json"))
            run = json.loads(item.pop("result_json"))
            item["answer"] = answer
            item["provenance"] = {key: run[key] for key in ("frame_id", "engine_id", "engine_version", "synthetic", "elapsed_ms", "usage")}
            results.append(item)
        return results

    def health(self) -> dict:
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            count = connection.execute("SELECT count(*) FROM observations").fetchone()[0]
        return {"database_schema": version, "observation_count": count}
