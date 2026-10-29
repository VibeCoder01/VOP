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
        self.preview_lock = Lock()
        self.skipped = 0
        self.previews = {}  # One masked/downscaled image per configured input (maximum 32).
        self.processed_previews = {}  # Completed answer frames; capture/test previews must not replace these.
        self.mask_grabs = {}  # One temporary, privacy-masked editor image per source.
        self._latest_preview = None
        self.stopping = False
        self.activity = None

    @property
    def latest_preview(self):
        return self._latest_preview

    @latest_preview.setter
    def latest_preview(self, value):
        if value is None:
            with self.preview_lock:
                self.previews.clear()
                self.processed_previews.clear()
                self.mask_grabs.clear()
                self._latest_preview = None
            if hasattr(self, 'live_previews'):
                self.live_previews.clear(None)
        else:
            self.remember_preview(*value)

    def remember_preview(self, source_id, frame_id, payload, captured_at=None):
        preview = (frame_id, payload, (captured_at or utcnow()).isoformat())
        with self.preview_lock:
            self.previews[source_id] = preview
            self._latest_preview = (source_id, frame_id, payload)
        return preview

    def clear_preview(self, source_id, frame_id=None):
        if frame_id is None and hasattr(self, 'live_previews'):
            self.live_previews.clear(source_id)
        with self.preview_lock:
            if frame_id is None:
                self.mask_grabs.pop(source_id, None)
            processed = self.processed_previews.get(source_id)
            if processed and (frame_id is None or processed[0] == frame_id):
                self.processed_previews.pop(source_id, None)
            item = self.previews.get(source_id)
            if item and (frame_id is None or frame_id == item[0]):
                self.previews.pop(source_id, None)
            if self._latest_preview and self._latest_preview[0] == source_id and (frame_id is None or self._latest_preview[1] == frame_id):
                self._latest_preview = None

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
            self.activity = {'source_id': source_id, 'stage': 'Preparing observation', 'started_at_utc': utcnow().isoformat()}
            if self.stopping:
                raise ProviderError('application_stopping', 'VOP is restarting. Wait for the workspace to reconnect.')
            source = self.source(source_id)
            if not source.questions:
                raise ProviderError("no_active_questions", "Enable at least one question before capturing")
            if getattr(self, 'auto_worker', None):
                self.activity = {**self.activity, 'stage': 'Connecting engine'}
                try:
                    self.auto_worker.ensure_ready()
                except ProviderError as exc:
                    self.save_capture_error(source, exc, stage='engine')
                    raise
            if frame is None:
                self.activity = {**self.activity, 'stage': 'Capturing image'}
                try:
                    frame = (self.live_previews.capture(source, self.capture_adapter.capture)
                             if hasattr(self, 'live_previews') else self.capture_adapter.capture(source))
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
            preview = preprocess(frame, source.settings.get("privacy_masks", []), preview=True)
            preview_token = self.remember_preview(source_id, frame.frame_id, preview.payload, frame.captured_at_utc)
            request = InferenceRequest(frame, source.questions, utcnow() + timedelta(seconds=self.settings.inference_timeout_seconds))
            records = [{"spec": q, "policy": self.store.policy(source_id, q.question_id, q.version)} for q in source.questions]
            if any(q.kind not in self.engine.capabilities() for q in source.questions):
                outcome = failed(request, self.engine, ProviderError("unsupported_kind", "Request exceeds declared engine capabilities", Status.UNSUPPORTED))
            else:
                self.activity = {**self.activity, 'stage': 'Answering questions'}
                groups = {}
                for record in records:
                    policy = record['policy']
                    groups.setdefault((policy.roi, policy.include_regions, policy.exclude_regions), []).append(record["spec"])
                outcomes = []
                masks = source.settings.get("privacy_masks", [])
                for (roi, include, exclude), group in groups.items():
                    # Strip original metadata for every backend before optional remote transmission.
                    input_frame = preprocess(frame, masks, roi, include_regions=include, exclude_regions=exclude)
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
            result["preprocessing"] = {"privacy_mask_count": len(source.settings.get("privacy_masks", [])),
                                       "roi_question_ids": [r["spec"].question_id for r in self.store.questions(source_id) if r["policy"].roi],
                                       'question_masks': {r['spec'].question_id: {'include': r['policy'].include_regions, 'exclude': r['policy'].exclude_regions}
                                                          for r in records if r['policy'].include_regions or r['policy'].exclude_regions}}
            self.activity = {**self.activity, 'stage': 'Saving result'}
            saved = self.store.save(source_id, frame, result, preview.payload if source.retain_evidence else None)
            with self.preview_lock:
                if self.previews.get(source_id) is preview_token:
                    self.processed_previews[source_id] = preview_token
            return saved
        finally:
            self.activity = None
            self.busy.release()

    def save_capture_error(self, source, error: ProviderError, *, stage='capture') -> dict:
        result = {"status": str(error.status), "engine_id": self.engine.engine_id,
                  "engine_version": self.engine.engine_version, "source_id": source.source_id,
                  "frame_id": None, "captured_at_utc": None, "processed_at_utc": utcnow().isoformat(),
                  "elapsed_ms": None, "synthetic": self.engine.synthetic, "usage": None, "provider_raw": None,
                  "failure_stage": stage,
                  "error": {"code": error.code, "message": "The engine was unavailable; capture was not attempted" if stage == 'engine' else "Source frame was unavailable", "status": str(error.status)},
                  "answers": [{"question_id": q.question_id, "question_version": q.version, "kind": str(q.kind),
                               "status": str(error.status), "value": None, "error": {"code": error.code}}
                              for q in source.questions]}
        return self.store.save(source.source_id, None, result)

    def record_gap(self, source_id: str, code: str = "source_disabled"):
        source = replace(self.sources[source_id], questions=tuple(r["spec"] for r in self.store.questions(source_id, active_only=True)))
        if source.questions:
            return self.save_capture_error(source, ProviderError(code, "Source is not being observed"))
