"""Operator-owned versioned JSON configuration; no secrets are accepted in it."""
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

from vop.contracts import AnswerKind, QuestionSpec
from vop.measurements import rectangle
from zoneinfo import ZoneInfo

ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ENV = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


def identifier(value: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("IDs must be 1–64 letters, digits, dots, underscores or hyphens")
    return value


def keys(data: dict, allowed: set[str]) -> None:
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError("Unknown configuration fields")


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    name: str
    kind: str
    settings: dict
    questions: tuple[QuestionSpec, ...]
    enabled: bool = True
    retain_evidence: bool = False
    sample_interval_seconds: float = 0

    def public(self) -> dict:
        return {"source_id": self.source_id, "name": self.name, "kind": self.kind,
                "enabled": self.enabled, "questions": [q.question_id for q in self.questions],
                "retain_evidence": self.retain_evidence, "sample_interval_seconds": self.sample_interval_seconds}


@dataclass(frozen=True)
class Settings:
    database: Path
    sources: tuple[SourceSpec, ...]
    engine_id: str
    mock_answers: dict
    capture_timeout_seconds: float = 10
    inference_timeout_seconds: float = 30
    timezone_name: str = "Europe/London"


def load_config(path: str | Path) -> Settings:
    try:
        return _load_config(path)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ValueError("Invalid or missing Phase 1 configuration field") from exc


def _load_config(path: str | Path) -> Settings:
    path = Path(path).resolve()
    def reject_constant(value):
        raise ValueError("Nonfinite numbers are not permitted in configuration")
    data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    keys(data, {"schema_version", "database", "engine", "sources", "capture_timeout_seconds", "inference_timeout_seconds", "timezone"})
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported configuration schema version")
    engine = data["engine"]
    keys(engine, {"kind", "id", "answers"})
    if engine.get("kind") != "mock" or not isinstance(engine.get("answers"), dict):
        raise ValueError("Service CLI supports configured mock engines; real engines require explicit Python injection")
    engine_id = identifier(engine["id"])
    timeouts = [data.get("capture_timeout_seconds", 10), data.get("inference_timeout_seconds", 30)]
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or not 0 < t <= 300 for t in timeouts):
        raise ValueError("Timeouts must be finite numbers in (0, 300]")
    sources = []
    for raw in data["sources"]:
        keys(raw, {"id", "name", "kind", "settings", "questions", "enabled", "retain_evidence", "sample_interval_seconds"})
        source_id = identifier(raw["id"])
        name = raw.get("name", source_id)
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise ValueError("Source name must be 1–128 characters")
        enabled = raw.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        kind, options = raw["kind"], raw.get("settings", {})
        allowed = {"synthetic": set(), "file": {"path"}, "usb": {"device"},
                   "rtsp": {"endpoint_env", "allowed_hosts"}, "snapshot": {"endpoint_env", "allowed_hosts"}}
        if kind not in allowed:
            raise ValueError("Unsupported source kind")
        keys(options, allowed[kind] | {"privacy_masks"})
        options = dict(options)
        masks = options.get("privacy_masks", [])
        if not isinstance(masks, list):
            raise ValueError("Privacy masks must be a list of normalised rectangles")
        for mask in masks:
            if rectangle(mask) is None:
                raise ValueError("Privacy masks require actual rectangles")
        if kind == "file":
            options["path"] = str((path.parent / options["path"]).resolve())
        if kind == "usb" and (type(options.get("device")) is not int or not 0 <= options["device"] <= 32):
            raise ValueError("USB device must be an index in [0, 32]")
        if kind in ("rtsp", "snapshot"):
            if not ENV.fullmatch(options.get("endpoint_env", "")):
                raise ValueError("Camera endpoint must reference an environment variable")
            hosts = options.get("allowed_hosts")
            if not isinstance(hosts, list) or not hosts or any(not isinstance(h, str) or not h or any(c in h for c in "/@* ") for h in hosts):
                raise ValueError("Camera requires explicit literal allowed_hosts")
        questions = []
        for q in raw["questions"]:
            keys(q, {"id", "version", "text", "kind", "choices", "levels", "threshold"})
            if (not isinstance(q.get("text"), str) or not isinstance(q.get("choices", []), list)
                or any(not isinstance(v, list) or len(v) != 2 or any(not isinstance(t, str) for t in v) for v in q.get("choices", []))
                or not isinstance(q.get("levels", []), list) or any(not isinstance(v, str) for v in q.get("levels", []))):
                raise ValueError("Question text and criterion descriptions must be strings")
            spec = QuestionSpec(identifier(q["id"]), identifier(q["version"]), q["text"], AnswerKind(q["kind"]),
                                tuple(tuple(v) for v in q.get("choices", [])), tuple(q.get("levels", [])), q.get("threshold", 0.5))
            if len(spec.text) > 4096:
                raise ValueError("Question text exceeds 4096 characters")
            questions.append(spec)
        if not 1 <= len(questions) <= 32 or len({q.question_id for q in questions}) != len(questions):
            raise ValueError("Source requires 1–32 distinct questions")
        evidence = raw.get("retain_evidence", False)
        interval = raw.get("sample_interval_seconds", 0)
        if type(evidence) is not bool or isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or not (interval == 0 or 1 <= interval <= 3600):
            raise ValueError("Evidence must be boolean; sampling is disabled (0) or 1–3600 seconds")
        sources.append(SourceSpec(source_id, name, kind, options, tuple(questions), enabled, evidence, interval))
    if not sources or len(sources) > 32 or len({s.source_id for s in sources}) != len(sources):
        raise ValueError("Configuration requires 1–32 distinct sources")
    zone = data.get("timezone", "Europe/London")
    ZoneInfo(zone)
    return Settings((path.parent / data["database"]).resolve(), tuple(sources), engine_id, dict(engine["answers"]), *timeouts, zone)
