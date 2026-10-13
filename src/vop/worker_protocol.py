"""Bounded JSON byte transport. No model imports and no shared filesystem."""
import base64
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
import json

from vop.config import identifier
from vop.contracts import AnswerKind, FrameEnvelope, InferenceRequest, InferenceResult, ProviderError, QuestionAnswer, QuestionSpec, Status, json_default, utcnow
from vop.inputs.file_image import FileImageAdapter
from vop.inputs.sources import MAX_IMAGE_BYTES
from vop.measurements import utc

MAX_BODY = 29 * 1024 * 1024
MAX_RESPONSE = 2 * 1024 * 1024


def encode(value):
    return json.dumps(value, default=json_default, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()


def request_body(request, worker_id):
    deadline = request.deadline_utc or utcnow() + timedelta(seconds=30)
    frame = asdict(request.frame)
    frame["payload"] = base64.b64encode(frame["payload"]).decode("ascii")
    content = {"frame": frame, "questions": [asdict(q) for q in request.questions]}
    # Different ROI byte hashes and criteria create distinct identities for the same original frame.
    fingerprint = sha256(encode(content)).hexdigest()
    return {"protocol": 1, "worker_id": worker_id, "request_id": fingerprint, "created_at_utc": utcnow(), "deadline_utc": deadline, **content}


def decode_request(body, worker_id):
    if not isinstance(body, dict) or set(body) != {"protocol", "worker_id", "request_id", "created_at_utc", "deadline_utc", "frame", "questions"} or type(body["protocol"]) is not int or body["protocol"] != 1 or body["worker_id"] != worker_id:
        raise ValueError("Invalid worker protocol or identity")
    now, created, deadline = utcnow(), utc(body["created_at_utc"]), utc(body["deadline_utc"])
    if created > now + timedelta(seconds=5) or created < now - timedelta(seconds=30) or deadline <= now or not created < deadline <= created + timedelta(seconds=300):
        raise ValueError("Expired request or excessive clock skew")
    content = {"frame": body["frame"], "questions": body["questions"]}
    fingerprint = sha256(encode(content)).hexdigest()
    if body["request_id"] != fingerprint:
        raise ValueError("Request digest does not match content")
    raw = dict(body["frame"])
    if set(raw) != set(FrameEnvelope.__dataclass_fields__):
        raise ValueError("Invalid frame fields")
    identifier(raw["source_id"])
    identifier(raw["frame_id"])
    if type(raw["width"]) is not int or type(raw["height"]) is not int or not 1 <= raw["width"] <= 8192 or not 1 <= raw["height"] <= 8192 or raw["width"] * raw["height"] > 16_000_000:
        raise ValueError("Worker image pixel limit exceeded")
    if not isinstance(raw["payload"], str) or len(raw["payload"]) > (MAX_IMAGE_BYTES + 2) // 3 * 4:
        raise ValueError("Worker image byte limit exceeded")
    pixels = base64.b64decode(raw["payload"], validate=True)
    if sha256(pixels).hexdigest() != raw["sha256"]:
        raise ValueError("Image digest mismatch")
    from PIL import Image
    from io import BytesIO
    with Image.open(BytesIO(pixels)) as header:
        if header.size != (raw["width"], raw["height"]):
            raise ValueError("Image dimensions do not match declared bounded metadata")
    checked = FileImageAdapter().from_bytes(pixels, raw["source_id"])
    if (checked.width, checked.height, checked.content_type) != (raw["width"], raw["height"], raw["content_type"]):
        raise ValueError("Image metadata mismatch")
    frame = FrameEnvelope(**{**raw, "payload": pixels, "captured_at_utc": utc(raw["captured_at_utc"]), "received_at_utc": utc(raw["received_at_utc"])})
    if frame.captured_at_utc > created + timedelta(seconds=5) or frame.received_at_utc > created + timedelta(seconds=5) or frame.captured_at_utc < created - timedelta(seconds=300):
        raise ValueError("Stale frame or inconsistent frame clock")
    if not isinstance(body["questions"], list) or not 1 <= len(body["questions"]) <= 32:
        raise ValueError("Worker requires 1–32 questions")
    questions = []
    for raw_question in body["questions"]:
        if not isinstance(raw_question, dict) or set(raw_question) != set(QuestionSpec.__dataclass_fields__):
            raise ValueError("Invalid question fields")
        q = dict(raw_question)
        identifier(q["question_id"])
        identifier(q["version"])
        if isinstance(q["threshold"], bool) or not isinstance(q["threshold"], (int, float)):
            raise ValueError("Question threshold must be numeric")
        if not isinstance(q["text"], str) or len(q["text"]) > 4096 or not isinstance(q["choices"], list) or len(q["choices"]) > 32 or not isinstance(q["levels"], list):
            raise ValueError("Invalid question limits")
        if any(not isinstance(v, list) or len(v) != 2 or any(not isinstance(s, str) or len(s) > 4096 for s in v) for v in q["choices"]) or any(not isinstance(s, str) or len(s) > 4096 for s in q["levels"]):
            raise ValueError("Invalid criteria")
        q.update(kind=AnswerKind(q["kind"]), choices=tuple(tuple(v) for v in q["choices"]), levels=tuple(q["levels"]))
        questions.append(QuestionSpec(**q))
    return InferenceRequest(frame, tuple(questions), deadline)


def decode_result(raw, request, engine_id, version):
    if not isinstance(raw, dict) or set(raw) != set(InferenceResult.__dataclass_fields__):
        raise ValueError("Invalid result fields")
    result = dict(raw)
    if (result["source_id"], result["frame_id"], result["engine_id"], result["engine_version"]) != (request.frame.source_id, request.frame.frame_id, engine_id, version):
        raise ValueError("Result provenance mismatch")
    result["status"] = Status(result["status"])
    import math
    if isinstance(result["elapsed_ms"], bool) or not isinstance(result["elapsed_ms"], (int, float)) or not math.isfinite(result["elapsed_ms"]) or result["elapsed_ms"] < 0:
        raise ValueError("Invalid inference duration")
    result["captured_at_utc"] = utc(result["captured_at_utc"])
    result["processed_at_utc"] = utc(result["processed_at_utc"])
    if result["captured_at_utc"] != request.frame.captured_at_utc or type(result["synthetic"]) is not bool or not isinstance(result["answers"], list):
        raise ValueError("Invalid result metadata")
    def error(value):
        if value is None:
            return None
        return ProviderError(value["code"], "Worker reported an inference failure", Status(value["status"]))
    answers = []
    for raw_answer in result["answers"]:
        if set(raw_answer) != set(QuestionAnswer.__dataclass_fields__):
            raise ValueError("Invalid answer fields")
        a = dict(raw_answer)
        a.update(kind=AnswerKind(a["kind"]), status=Status(a["status"]), error=error(a["error"]))
        answers.append(QuestionAnswer(**a))
    if [(a.question_id, a.question_version, a.kind) for a in answers] != [(q.question_id, q.version, q.kind) for q in request.questions]:
        raise ValueError("Answer coverage mismatch")
    result.update(answers=tuple(answers), error=error(result["error"]))
    return InferenceResult(**result)
