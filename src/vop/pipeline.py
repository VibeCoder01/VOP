"""One in-flight frame, zero queued frames; callers see explicit overload outcomes."""
from dataclasses import asdict, replace
from datetime import timedelta
import json
import math
from threading import Lock

from vop.config import Settings
from vop.contracts import FrameEnvelope, InferenceEngine, InferenceRequest, ProviderError, Status, failed, infer, json_default, utcnow
from vop.inputs.sources import FrameSource, SourceAdapters
from vop.storage import Store


class Pipeline:
    def __init__(self, settings: Settings, engine: InferenceEngine, store: Store, capture: FrameSource | None = None):
        self.settings, self.engine, self.store = settings, engine, store
        self.capture_adapter = capture or SourceAdapters(timeout_seconds=settings.capture_timeout_seconds)
        self.sources = {s.source_id: s for s in settings.sources}
        self.busy = Lock()
        self.skipped = 0

    def source(self, source_id: str):
        if source_id not in self.sources:
            raise ProviderError("source_not_found", "Source does not exist")
        source = self.sources[source_id]
        if not source.enabled:
            raise ProviderError("source_disabled", "Source is disabled")
        return source

    def run(self, source_id: str, frame=None) -> dict:
        source = self.source(source_id)
        if not self.busy.acquire(blocking=False):
            self.skipped += 1
            self.store.audit("capture_skipped", "overload")
            raise ProviderError("overloaded", "An inference is in flight; this request was not queued")
        try:
            if frame is None:
                try:
                    frame = self.capture_adapter.capture(source)
                except ProviderError as exc:
                    return self.save_capture_error(source, exc)
                except Exception:
                    return self.save_capture_error(source, ProviderError("capture_failed", "Capture failed"))
            if not isinstance(frame, FrameEnvelope):
                return self.save_capture_error(source, ProviderError("capture_contract", "Adapter did not return a FrameEnvelope"))
            if frame.source_id != source_id:
                raise ProviderError("source_mismatch", "Frame source does not match configured source")
            previous = self.store.previous(source_id, frame.frame_id)
            if previous:
                if previous.pop("sha256") != frame.sha256:
                    raise ProviderError("frame_conflict", "Frame ID was reused for different content")
                return {**previous, "duplicate": True}
            request = InferenceRequest(frame, source.questions, utcnow() + timedelta(seconds=self.settings.inference_timeout_seconds))
            if any(q.kind not in self.engine.capabilities() for q in source.questions):
                outcome = failed(request, self.engine, ProviderError("unsupported_kind", "Request exceeds declared engine capabilities", Status.UNSUPPORTED))
            else:
                outcome = infer(self.engine, request)
            expected = [(q.question_id, q.version, q.kind) for q in source.questions]
            returned = [(a.question_id, a.question_version, a.kind) for a in outcome.answers]
            invalid_value = any(a.status == Status.SUCCESS and not (
                q.kind == "binary" and isinstance(a.value, bool)
                or q.kind == "choice" and isinstance(a.value, str) and a.value in dict(q.choices)
                or q.kind == "ordinal" and isinstance(a.value, (int, float)) and not isinstance(a.value, bool)
                and math.isfinite(a.value) and 0 <= a.value <= len(q.levels) - 1)
                for q, a in zip(source.questions, outcome.answers))
            if (returned != expected or invalid_value or outcome.frame_id != frame.frame_id or outcome.source_id != source_id
                or outcome.engine_id != self.engine.engine_id or outcome.engine_version != self.engine.engine_version
                or outcome.synthetic != self.engine.synthetic or outcome.captured_at_utc != frame.captured_at_utc):
                outcome = failed(request, self.engine, ProviderError("provider_contract", "Provider provenance or question coverage did not match request"))
            try:
                result = json.loads(json.dumps(asdict(outcome), default=json_default, allow_nan=False))
            except (TypeError, ValueError):
                outcome = failed(request, self.engine, ProviderError("provider_contract", "Provider fields are not finite JSON values"))
                result = json.loads(json.dumps(asdict(outcome), default=json_default, allow_nan=False))
            return self.store.save(source_id, frame, result)
        finally:
            self.busy.release()

    def save_capture_error(self, source, error: ProviderError) -> dict:
        result = {"status": str(error.status), "engine_id": self.engine.engine_id,
                  "engine_version": self.engine.engine_version, "source_id": source.source_id,
                  "frame_id": None, "captured_at_utc": None, "processed_at_utc": utcnow().isoformat(),
                  "elapsed_ms": None, "synthetic": self.engine.synthetic, "usage": None, "provider_raw": None,
                  "error": {"code": error.code, "message": "Source frame was unavailable", "status": str(error.status)},
                  "answers": [{"question_id": q.question_id, "question_version": q.version, "kind": str(q.kind),
                               "status": str(error.status), "value": None, "error": {"code": error.code}}
                              for q in source.questions]}
        return self.store.save(source.source_id, None, result)
