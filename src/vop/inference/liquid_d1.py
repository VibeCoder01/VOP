"""Only this adapter knows Liquid's model, question schema and native fields."""
from copy import deepcopy
from io import BytesIO
import math
from pathlib import Path
from time import perf_counter
from typing import Any

from PIL import Image

from vop.contracts import (AnswerKind, InferenceRequest, InferenceResult, ProviderError,
                           QuestionAnswer, QuestionSpec, Status, result)

MODEL_ID = "LiquidAI/d1-3B"
# Official pin: actual CPU validation in Phase 0 and CUDA/BF16 validation in Phase 4.
CHECKPOINT_REVISION = "051bcc464b01b9f92942b364d9586b0ef5912432"
TYPE_MAP = {AnswerKind.BINARY: "noul", AnswerKind.CHOICE: "choice", AnswerKind.ORDINAL: "score"}


def provider_questions(questions: tuple[QuestionSpec, ...]) -> dict:
    output = {}
    for q in questions:
        spec = {"type": TYPE_MAP[q.kind], "instructions": q.text}
        if q.kind == AnswerKind.CHOICE:
            spec["criteria"] = dict(q.choices)
        elif q.kind == AnswerKind.ORDINAL:
            spec["criteria"] = list(q.levels)
        output[q.question_id] = spec
    return output


def number(value: Any, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Expected a numeric provider field")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Provider number is nonfinite or outside its declared range")
    return float(value)


def normalise(q: QuestionSpec, raw: Any) -> QuestionAnswer:
    """Validate native fields; retain everything, including extension fields."""
    saved = deepcopy(raw)
    try:
        if not isinstance(raw, dict):
            raise ValueError("Answer must be an object")
        if raw.get("type") == "unsupported":
            return QuestionAnswer(q.question_id, q.version, q.kind, Status.UNSUPPORTED,
                                  raw_provider_fields=saved,
                                  error=ProviderError("unsupported_answer", "Provider declined question", Status.UNSUPPORTED))
        if raw.get("type") != TYPE_MAP[q.kind]:
            raise ValueError("Answer type does not match requested kind")
        if q.kind == AnswerKind.BINARY:
            score = number(raw["noul"], 0, 1)
            return QuestionAnswer(q.question_id, q.version, q.kind, Status.SUCCESS,
                                  score >= q.threshold, saved, score, "Liquid noul: model score for yes",
                                  q.threshold)
        keys = set(dict(q.choices)) if q.kind == AnswerKind.CHOICE else {str(i) for i in range(len(q.levels))}
        probs = raw["probabilities"]
        if not isinstance(probs, dict) or set(probs) != keys:
            raise ValueError("Probabilities do not match criteria")
        for p in probs.values():
            number(p, 0, 1)
        if not math.isclose(sum(probs.values()), 1.0, abs_tol=1e-4):
            raise ValueError("Probabilities do not sum to one")
        confidence = number(raw["confidence"], 0, 1)
        if not math.isclose(confidence, max(probs.values()), abs_tol=1e-4):
            raise ValueError("Confidence differs from maximum native probability")
        if q.kind == AnswerKind.CHOICE:
            value = raw["choice"]
            if not isinstance(value, str) or value not in keys or not math.isclose(probs[value], confidence, abs_tol=1e-4):
                raise ValueError("Selected choice is invalid")
        else:
            value = number(raw["score"], 0, len(q.levels) - 1)
            if raw["legend"] != {str(i): text for i, text in enumerate(q.levels)}:
                raise ValueError("Legend differs from requested ordered levels")
            if not math.isclose(value, sum(int(k) * p for k, p in probs.items()), abs_tol=1e-4):
                raise ValueError("Score differs from expected level")
        return QuestionAnswer(q.question_id, q.version, q.kind, Status.SUCCESS, value, saved,
                              confidence, "Liquid confidence: maximum option probability")
    except (KeyError, ValueError, TypeError) as exc:
        return QuestionAnswer(q.question_id, q.version, q.kind, Status.MODEL_FAILURE,
                              raw_provider_fields=saved,
                              error=ProviderError("malformed_answer", str(exc)))


class LiquidD1InferenceAdapter:
    engine_id = "liquid-d1-3b"
    engine_version = CHECKPOINT_REVISION
    synthetic = False

    def __init__(self, *, device: str = "cpu", precision: str = "float32") -> None:
        if device not in ("cpu", "cuda:0") or precision not in ("float32", "float16", "bfloat16") or device == "cpu" and precision != "float32":
            raise ValueError("Supported runtimes: CPU FP32 or CUDA device 0 with explicit precision")
        self.device, self.precision = device, precision
        self.model = None
        self.snapshot_path: str | None = None
        self.download_ms: float | None = None
        self.model_load_ms: float | None = None

    def capabilities(self) -> tuple[AnswerKind, ...]:
        return tuple(AnswerKind)

    def load(self, *, allow_model_download: bool = False, accept_model_risk: bool = False,
             cache_dir: str | Path | None = None) -> None:
        if not allow_model_download or not accept_model_risk:
            raise ProviderError("consent_required", "Explicit download and model-code/RAM risk consent required")
        try:
            import torch
            from huggingface_hub import snapshot_download
            from transformers import AutoModel
        except ImportError as exc:
            raise ProviderError("dependency_missing", str(exc)) from exc
        started = perf_counter()
        self.snapshot_path = snapshot_download(MODEL_ID, revision=CHECKPOINT_REVISION,
                                               cache_dir=cache_dir)
        self.download_ms = (perf_counter() - started) * 1000
        if Path(self.snapshot_path).name != CHECKPOINT_REVISION:
            raise ProviderError("revision_mismatch", "Snapshot directory does not match approved SHA")
        # Local snapshot also pins the model's internal tokenizer/processor lookups.
        started = perf_counter()
        try:
            if self.device != "cpu" and not torch.cuda.is_available():
                raise ProviderError("gpu_unavailable", "Requested GPU runtime is unavailable; no CPU fallback")
            placement = {"device_map": {"": self.device}} if self.device != "cpu" else {}
            self.model = AutoModel.from_pretrained(self.snapshot_path, revision=CHECKPOINT_REVISION,
                                                   code_revision=CHECKPOINT_REVISION,
                                                   trust_remote_code=True, local_files_only=True,
                                                   dtype=getattr(torch, self.precision), **placement).to(self.device)
            self.model.eval()
        finally:
            self.model_load_ms = (perf_counter() - started) * 1000

    def infer(self, request: InferenceRequest) -> InferenceResult:
        if self.model is None:
            raise ProviderError("model_not_loaded", "Load the optional model explicitly first")
        started = perf_counter()
        with Image.open(BytesIO(request.frame.payload)) as image:
            raw = self.model.system_one(None, provider_questions(request.questions), images=[image.convert("RGB")])
        elapsed = (perf_counter() - started) * 1000
        error = None
        if not isinstance(raw, dict) or not isinstance(raw.get("answers"), dict) or not isinstance(raw.get("usage"), dict):
            error = ProviderError("malformed_response", "Expected top-level answers and usage objects")
        else:
            usage = raw["usage"]
            if (set(raw["answers"]) != {q.question_id for q in request.questions}
                or any(isinstance(usage.get(k), bool) or not isinstance(usage.get(k), int)
                       or usage[k] < 0 for k in ("input_tokens", "output_tokens"))
                or usage["output_tokens"] != 0):
                error = ProviderError("malformed_response", "Question coverage or usage is invalid")
        if error:
            answers = tuple(QuestionAnswer(q.question_id, q.version, q.kind, Status.MODEL_FAILURE, error=error)
                            for q in request.questions)
        else:
            answers = tuple(normalise(q, raw["answers"][q.question_id]) for q in request.questions)
        usage = deepcopy(raw.get("usage")) if isinstance(raw, dict) else None
        if isinstance(usage, dict):
            usage["runtime"] = {"device": self.device, "precision": self.precision}
        return result(request, self, answers, elapsed, deepcopy(raw), usage, error)
