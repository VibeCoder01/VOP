"""Versioned SQLite foundation. No image pixels or secret values are stored."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from vop.config import Settings
from vop.contracts import json_default, utcnow

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


def dumps(value) -> str:
    return json.dumps(value, default=json_default, allow_nan=False, sort_keys=True)


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("Database schema is newer than this application; restore/use compatible software")
            if version == 0:
                if connection.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchone():
                    raise ValueError("Refusing to adopt an unversioned nonempty database")
                connection.executescript(SCHEMA)
            connection.execute("PRAGMA journal_mode=WAL")

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
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
                    connection.execute("UPDATE sources SET configuration=?,status=CASE WHEN ?=0 THEN 'DISABLED' WHEN status='DISABLED' THEN 'CONNECTING' ELSE status END WHERE id=?",
                                       (configuration, source.enabled, source.source_id))
                else:
                    connection.execute("INSERT INTO sources VALUES(?,?,?,NULL)",
                                       (source.source_id, configuration, "CONNECTING" if source.enabled else "DISABLED"))
                for question in source.questions:
                    spec = dumps(asdict(question))
                    key = (source.source_id, question.question_id, question.version)
                    saved = connection.execute("SELECT specification FROM question_versions WHERE source_id=? AND question_id=? AND version=?", key).fetchone()
                    if saved and saved[0] != spec:
                        raise ValueError("Question version already exists with different content; increment version")
                    if not saved:
                        connection.execute("INSERT INTO question_versions VALUES(?,?,?,?)", (*key, spec))

    def audit(self, action: str, outcome: str) -> None:
        with self.connection() as connection:
            connection.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), action, outcome))

    def sources(self, source_ids: tuple[str, ...]) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM sources").fetchall()
        return [{**json.loads(r["configuration"]), "status": r["status"], "last_frame_utc": r["last_frame_utc"]}
                for r in rows if r["id"] in source_ids]

    def previous(self, source_id: str, frame_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT r.id,r.result_json,f.sha256 FROM runs r JOIN frames f USING(source_id,frame_id) WHERE r.source_id=? AND r.frame_id=?", (source_id, frame_id)).fetchone()
        return {"run_id": row["id"], "result": json.loads(row["result_json"]), "sha256": row["sha256"]} if row else None

    def save(self, source_id: str, frame, result: dict) -> dict:
        run_id = str(uuid4())
        processed = result["processed_at_utc"]
        with self.connection() as connection:
            if frame:
                connection.execute("INSERT INTO frames VALUES(?,?,?,?,?,?,?,?)", (source_id, frame.frame_id,
                                   frame.captured_at_utc.isoformat(), frame.received_at_utc.isoformat(), frame.sha256,
                                   frame.width, frame.height, frame.content_type))
            connection.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (run_id, source_id, result["frame_id"], processed, dumps(result)))
            for answer in result["answers"]:
                value = answer["value"]
                state = ("positive" if value is True else "negative" if value is False else "not_applicable") if answer["status"] == "success" else "error"
                connection.execute("INSERT INTO observations(id,run_id,source_id,question_id,question_version,captured_at_utc,processed_at_utc,status,normalised_state,answer_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   (str(uuid4()), run_id, source_id, answer["question_id"], answer["question_version"],
                                    result["captured_at_utc"], processed, answer["status"], state, dumps(answer)))
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
