"""Small value contracts: frames carry bytes, never a required shared path."""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import math
from time import perf_counter
from typing import Any, Protocol


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Status(StrEnum):
    SUCCESS = "success"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"
    MODEL_FAILURE = "model_failure"


class AnswerKind(StrEnum):
    BINARY = "binary"
    CHOICE = "choice"
    ORDINAL = "ordinal"


@dataclass
class ProviderError(Exception):
    code: str
    message: str
    status: Status = Status.MODEL_FAILURE

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True)
class FrameEnvelope:
    source_id: str
    frame_id: str
    captured_at_utc: datetime
    received_at_utc: datetime
    content_type: str
    payload: bytes = field(repr=False)
    width: int
    height: int
    sha256: str

    def __post_init__(self) -> None:
        for stamp in (self.captured_at_utc, self.received_at_utc):
            if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
                raise ValueError("Frame timestamps must be UTC")
        if not self.source_id or not self.frame_id or not self.payload:
            raise ValueError("Frame requires source, identity and image bytes")


@dataclass(frozen=True)
class QuestionSpec:
    question_id: str
    version: str
    text: str
    kind: AnswerKind
    choices: tuple[tuple[str, str], ...] = ()
    levels: tuple[str, ...] = ()
    threshold: float = 0.5

    def __post_init__(self) -> None:
        if not self.question_id or not self.version or not self.text.strip():
            raise ValueError("Question ID, version and text are required")
        if self.kind not in set(AnswerKind):
            raise ValueError("Unknown answer kind")
        if not math.isfinite(self.threshold) or not 0 <= self.threshold <= 1:
            raise ValueError("Threshold must be finite and in [0, 1]")
        if self.kind == AnswerKind.CHOICE:
            names = [n for n, d in self.choices if n and d]
            if len(names) < 2 or len(names) != len(self.choices) or len(set(names)) != len(names):
                raise ValueError("Choice requires distinct named options and descriptions")
        if self.kind == AnswerKind.ORDINAL and not (2 <= len(self.levels) <= 10 and all(self.levels)):
            raise ValueError("Ordinal requires 2–10 ordered descriptions")


@dataclass(frozen=True)
class InferenceRequest:
    frame: FrameEnvelope
    questions: tuple[QuestionSpec, ...]
    deadline_utc: datetime | None = None

    def __post_init__(self) -> None:
        ids = [q.question_id for q in self.questions]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("Request requires unique named questions")
        if self.deadline_utc is not None and (
            self.deadline_utc.utcoffset() is None or self.deadline_utc.utcoffset().total_seconds() != 0
        ):
            raise ValueError("Deadline must be UTC")


@dataclass(frozen=True)
class QuestionAnswer:
    question_id: str
    question_version: str
    kind: AnswerKind
    status: Status
    value: bool | str | float | None = None
    raw_provider_fields: Any = None
    score: float | None = None
    score_semantics: str | None = None
    threshold_used: float | None = None
    calibrated: bool = False
    error: ProviderError | None = None

    def __post_init__(self) -> None:
        if self.status != Status.SUCCESS and self.value is not None:
            raise ValueError("Failed/unsupported answers cannot assert an observation")


@dataclass(frozen=True)
class InferenceResult:
    status: Status
    engine_id: str
    engine_version: str
    source_id: str
    frame_id: str
    captured_at_utc: datetime
    processed_at_utc: datetime
    answers: tuple[QuestionAnswer, ...]
    elapsed_ms: float
    provider_raw: Any = None
    usage: Any = None
    error: ProviderError | None = None
    synthetic: bool = False


class InferenceEngine(Protocol):
    engine_id: str
    engine_version: str
    synthetic: bool

    def capabilities(self) -> tuple[AnswerKind, ...]: ...
    def infer(self, request: InferenceRequest) -> InferenceResult: ...


def result(request: InferenceRequest, engine: InferenceEngine, answers: tuple[QuestionAnswer, ...],
           elapsed_ms: float, raw: Any = None, usage: Any = None,
           error: ProviderError | None = None) -> InferenceResult:
    status = next((s for s in (Status.TIMEOUT, Status.MODEL_FAILURE, Status.UNSUPPORTED)
                   if any(a.status == s for a in answers)), Status.SUCCESS)
    return InferenceResult(status, engine.engine_id, engine.engine_version, request.frame.source_id,
                           request.frame.frame_id, request.frame.captured_at_utc, utcnow(), answers,
                           elapsed_ms, raw, usage, error, engine.synthetic)


def failed(request: InferenceRequest, engine: InferenceEngine, error: ProviderError,
           elapsed_ms: float = 0) -> InferenceResult:
    answers = tuple(QuestionAnswer(q.question_id, q.version, q.kind, error.status, error=error)
                    for q in request.questions)
    return result(request, engine, answers, elapsed_ms, error=error)


def infer(engine: InferenceEngine, request: InferenceRequest) -> InferenceResult:
    """Generic caller; synchronous deadlines are checked before and after the call.

    The real benchmark additionally enforces a hard child-process timeout.
    """
    started = perf_counter()
    try:
        if request.deadline_utc and utcnow() >= request.deadline_utc:
            raise ProviderError("deadline", "Request expired", Status.TIMEOUT)
        outcome = engine.infer(request)
        if request.deadline_utc and utcnow() >= request.deadline_utc:
            raise ProviderError("deadline", "Provider exceeded deadline", Status.TIMEOUT)
        return outcome
    except ProviderError as exc:
        return failed(request, engine, exc, (perf_counter() - started) * 1000)
    except TimeoutError as exc:
        return failed(request, engine, ProviderError("timeout", str(exc), Status.TIMEOUT),
                      (perf_counter() - started) * 1000)
    except MemoryError as exc:
        return failed(request, engine, ProviderError("inference_oom", str(exc)),
                      (perf_counter() - started) * 1000)
    except Exception as exc:
        return failed(request, engine, ProviderError("inference_exception", f"{type(exc).__name__}: {exc}"),
                      (perf_counter() - started) * 1000)


def json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")
