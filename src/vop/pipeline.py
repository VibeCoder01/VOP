"""One in-flight frame, zero queued frames; callers see explicit overload outcomes."""
from dataclasses import asdict, replace
from datetime import timedelta
import json
import math
from threading import Lock

from vop.config import Settings, SourceSpec
from vop.contracts import AnswerKind, QuestionSpec, FrameEnvelope, InferenceEngine, InferenceRequest, ProviderError, Status, failed, infer, json_default, utcnow, result as make_result
from vop.preprocessing import preprocess
from vop.inputs.sources import FrameSource, SourceAdapters
from vop.storage import Store


class Pipeline:
    def __init__(self, settings: Settings, engine: InferenceEngine, store: Store, capture: FrameSource | None = None):
        self.settings, self.engine, self.store = settings, engine, store
        self.capture_adapter = capture or SourceAdapters(timeout_seconds=settings.capture_timeout_seconds)
        self.sources = {s.source_id: s for s in settings.sources if not store.is_removed(s.source_id)}
        self.removed_sources = {s.source_id: s for s in settings.sources if store.is_removed(s.source_id)}
        with store.connection() as db:
            for row in db.execute("SELECT value_json FROM release_settings WHERE id LIKE 'retained_source:%'"):
                body = json.loads(row[0])
                questions = []
                for q in body['questions']:
                    q['kind'] = AnswerKind(q['kind'])
                    q['choices'] = tuple(tuple(v) for v in q.get('choices', []))
                    q['levels'] = tuple(q.get('levels', []))
                    questions.append(QuestionSpec(**q))
                body['questions'] = tuple(questions)
                source = SourceSpec(**body)
                target = self.removed_sources if store.is_removed(source.source_id) else self.sources
                target.setdefault(source.source_id, source)
        self.busy = Lock()
        self.skipped = 0
        self.latest_preview = None  # One privacy-masked, downscaled preview; never an unbounded cache.
        self.stopping = False

    def source(self, source_id: str):
        if source_id not in self.sources:
            raise ProviderError("source_not_found", "Source does not exist")
        source = self.sources[source_id]
        control = self.store.source_control(source_id)
        if not control["enabled"]:
            raise ProviderError("source_disabled", "Source is disabled")
        return replace(source, questions=tuple(q["spec"] for q in self.store.questions(source_id, active_only=True)),
                       retain_evidence=control["retain_evidence"], sample_interval_seconds=control["sample_interval_seconds"])

    def run(self, source_id: str, frame=None) -> dict:
        if not self.busy.acquire(blocking=False):
            self.skipped += 1
            self.store.audit("capture_skipped", "overload")
            raise ProviderError("overloaded", "An inference is in flight; this request was not queued")
        try:
            if self.stopping:
                raise ProviderError('application_stopping', 'VOP is restarting. Wait for the workspace to reconnect.')
            source = self.source(source_id)
            if not source.questions:
                raise ProviderError("no_active_questions", "Enable at least one question before capturing")
            if getattr(self, 'auto_worker', None):
                try:
                    self.auto_worker.ensure_ready()
                except ProviderError as exc:
                    self.save_capture_error(source, exc)
                    raise
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
                records = [{"spec": q, "policy": self.store.policy(source_id, q.question_id, q.version)} for q in source.questions]
                groups = {}
                for record in records:
                    groups.setdefault(record["policy"].roi, []).append(record["spec"])
                outcomes = []
                masks = source.settings.get("privacy_masks", [])
                for roi, group in groups.items():
                    # Strip original metadata for every backend before optional remote transmission.
                    input_frame = preprocess(frame, masks, roi)
                    group_request = InferenceRequest(input_frame, tuple(group), request.deadline_utc)
                    group_result = infer(self.engine, group_request)
                    if (group_result.frame_id != frame.frame_id or group_result.source_id != source_id
                        or group_result.engine_id != self.engine.engine_id or group_result.engine_version != self.engine.engine_version
                        or [(a.question_id, a.question_version) for a in group_result.answers] != [(q.question_id, q.version) for q in group]):
                        group_result = failed(group_request, self.engine, ProviderError("provider_contract", "Provider group provenance did not match request"))
                    outcomes.append(group_result)
                if len(outcomes) == 1:
                    outcome = outcomes[0]
                else:
                    answers = {a.question_id: a for r in outcomes for a in r.answers}
                    outcome = make_result(request, self.engine, tuple(answers[q.question_id] for q in source.questions),
                                          sum(r.elapsed_ms for r in outcomes), {"roi_groups": [r.provider_raw for r in outcomes]},
                                          {"roi_group_usage": [r.usage for r in outcomes]})
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
            preview = preprocess(frame, source.settings.get("privacy_masks", []), preview=True)
            self.latest_preview = (source_id, frame.frame_id, preview.payload)
            result["preprocessing"] = {"privacy_mask_count": len(source.settings.get("privacy_masks", [])),
                                       "roi_question_ids": [r["spec"].question_id for r in self.store.questions(source_id) if r["policy"].roi]}
            return self.store.save(source_id, frame, result, preview.payload if source.retain_evidence else None)
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

    def record_gap(self, source_id: str, code: str = "source_disabled"):
        source = replace(self.sources[source_id], questions=tuple(r["spec"] for r in self.store.questions(source_id, active_only=True)))
        if source.questions:
            return self.save_capture_error(source, ProviderError(code, "Source is not being observed"))
