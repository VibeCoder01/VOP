from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path

import pytest

from vop.config import load_config
from vop.contracts import ProviderError, utcnow
from vop.inference.mock import MockInferenceEngine
from vop.inputs.sources import capture_inline
from vop.measurements import QueryPolicy, replay
from vop.sampling import Sampler
from vop.service import create_app

TOKEN = "sampling-offline-key-" + "s" * 32


def test_camera_tests_take_priority_and_do_not_need_enabled_questions(settings):
    app = create_app(settings, token=TOKEN)
    pipeline = app.state.pipeline
    sid = 'synthetic-scene'
    pipeline.store.update_source(sid, enabled=True, retain_evidence=False, sample_interval_seconds=1)
    sampler = Sampler(pipeline)
    calls = []
    sampler.request_camera_test(sid, lambda: calls.append(pipeline.busy.locked()))
    sampler.request_camera_test(sid, lambda: pytest.fail('Duplicate test was not coalesced'))
    sampler.tick(1)
    assert calls == [True]
    assert pipeline.store.health()['observation_count'] == 0
    sampler.tick(2)
    assert pipeline.store.health()['observation_count'] == 3
    pipeline.store.update_source(sid, enabled=False, retain_evidence=False, sample_interval_seconds=0)
    sampler.request_camera_test(sid, lambda: calls.append(True))
    sampler.tick(3)
    assert calls == [True, True]
    assert not pipeline.busy.locked()


@pytest.fixture
def settings(tmp_path):
    body = json.loads((Path(__file__).resolve().parents[1] / "sample-config" / "phase1.json").read_text(encoding="utf-8"))
    body["database"] = "data.sqlite3"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return load_config(path)


def test_sampling_ticks_have_no_backlog_and_pause(settings):
    app = create_app(settings, token=TOKEN)
    app.state.store.update_source("synthetic-scene", enabled=True, retain_evidence=False, sample_interval_seconds=2)
    sampler = Sampler(app.state.pipeline)
    sampler.tick(10)
    assert app.state.store.health()["observation_count"] == 3
    sampler.tick(10.5)
    assert app.state.store.health()["observation_count"] == 3
    app.state.pipeline.busy.acquire()
    try:
        sampler.tick(12)
    finally:
        app.state.pipeline.busy.release()
    assert app.state.pipeline.skipped == 1
    sampler.tick(100)  # One new sample, never catches up 44 obsolete samples.
    assert app.state.store.health()["observation_count"] == 6
    app.state.store.update_source("synthetic-scene", enabled=False, retain_evidence=False, sample_interval_seconds=2)
    sampler.tick(200)
    assert app.state.store.health()["observation_count"] == 6


def test_inference_roi_groups_share_original_frame_and_privacy_mask(settings):
    seen = []
    class Inspect(MockInferenceEngine):
        def infer(self, request):
            seen.append((request.frame.frame_id, request.frame.width, tuple(q.question_id for q in request.questions)))
            return super().infer(request)
    source = replace(settings.sources[0], settings={"privacy_masks": [[0, 0, .2, 1]]})
    app = create_app(replace(settings, sources=(source,)), token=TOKEN, engine=Inspect(settings.mock_answers))
    q = app.state.store.questions(source.source_id)[0]["spec"]
    app.state.store.edit_question(source.source_id, q, QueryPolicy(roi=(0, 0, .5, 1)), expected_version="1")
    frame = capture_inline(source)
    result = app.state.pipeline.run(source.source_id, frame)
    assert len(seen) == 2 and {s[0] for s in seen} == {frame.frame_id}
    assert {s[1] for s in seen} == {192, 384}
    assert result["result"]["preprocessing"]["privacy_mask_count"] == 1
    assert len(result["result"]["answers"]) == 3


def test_late_frame_does_not_rewrite_materialised_episode(settings):
    app = create_app(settings, token=TOKEN)
    origin = utcnow() - timedelta(seconds=40)
    for seconds in (0, 10):
        app.state.pipeline.run("synthetic-scene", replace(capture_inline(settings.sources[0]), captured_at_utc=origin + timedelta(seconds=seconds)))
    before = app.state.store.events()
    app.state.pipeline.engine.configured["red_square"] = False
    app.state.pipeline.run("synthetic-scene", replace(capture_inline(settings.sources[0]), captured_at_utc=origin + timedelta(seconds=5)))
    assert app.state.store.events() == before
    late = app.state.store.observations(limit=100)[-3:]
    assert all(row["temporal_eligible"] == 0 for row in late)


def test_date_range_clips_duration_without_restarting_episode():
    origin = utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    rows = [{"id": str(i), "source_id": "s", "question_id": "q", "question_version": "1",
             "captured_at_utc": (origin + timedelta(seconds=i * 10)).isoformat(),
             "processed_at_utc": (origin + timedelta(seconds=i * 10)).isoformat(),
             "status": "success", "answer": {"value": value}} for i, value in enumerate((True, True, True, False, False))]
    value = replay(rows, QueryPolicy(), range_start=origin + timedelta(seconds=15), range_end=origin + timedelta(seconds=35))
    assert value["episode_count"] == 0  # Episode began before the selected window.
    assert value["estimated_active_seconds"] == 20 and value["covered_seconds"] == 20
    assert value["occupancy_fraction"] == 1


def test_failed_capture_does_not_invent_last_observed_time(settings):
    app = create_app(settings, token=TOKEN)
    app.state.pipeline.save_capture_error(settings.sources[0], ProviderError("missing", "Missing"))
    summary = app.state.store.summary("synthetic-scene", "red_square", "1")
    assert summary["state"] == "UNKNOWN" and summary["last_observed_at_utc"] is None
    assert summary["last_sample_at_utc"] is not None


def test_multiple_cameras_take_round_robin_turns_without_backlog(settings, monkeypatch):
    first = settings.sources[0]
    sources = tuple(replace(first, source_id=sid, name=sid) for sid in ('camera-a', 'camera-b', 'camera-c'))
    app = create_app(replace(settings, sources=sources), token=TOKEN)
    for source in sources:
        app.state.store.update_source(source.source_id, enabled=True, retain_evidence=False, sample_interval_seconds=2)
    turns = []
    def run(source_id):
        turns.append(source_id)
        return {'result': {'status': 'success'}}
    monkeypatch.setattr(app.state.pipeline, 'run', run)
    sampler = Sampler(app.state.pipeline)
    for _ in range(4): sampler.tick(10)
    assert turns == ['camera-a', 'camera-b', 'camera-c']
    sampler.tick(100)  # One fresh turn, never catches up obsolete frames.
    assert turns == ['camera-a', 'camera-b', 'camera-c', 'camera-a']
    app.state.store.update_source('camera-b', enabled=True, retain_evidence=False, sample_interval_seconds=0)
    sampler.tick(100)
    assert turns[-1] == 'camera-c'
    sampler.tick(100)
    assert len(turns) == 5
    # A failed input yields the next turn and retains per-camera backoff.
    def fail_first(source_id):
        turns.append(source_id)
        if source_id == 'camera-a': return {'result': {'status': 'model_failure'}}
        return {'result': {'status': 'success'}}
    monkeypatch.setattr(app.state.pipeline, 'run', fail_first)
    sampler.tick(102)
    sampler.tick(102)
    assert turns[-2:] == ['camera-a', 'camera-c']
    assert sampler.deadlines['camera-a'] == 106


def test_manual_turn_coalesces_and_takes_fresh_frame_without_enabling_monitoring(settings):
    app = create_app(settings, token=TOKEN)
    store, pipeline = app.state.store, app.state.pipeline
    store.update_source('synthetic-scene', enabled=True, retain_evidence=False, sample_interval_seconds=0)
    sampler = Sampler(pipeline)
    assert sampler.request('synthetic-scene')
    assert not sampler.request('synthetic-scene')
    count = store.health()['observation_count']
    pipeline.busy.acquire()
    try:
        sampler.tick(10)
        assert sampler.requested('synthetic-scene')
        assert store.health()['observation_count'] == count
    finally:
        pipeline.busy.release()
    sampler.tick(11)
    assert not sampler.requested('synthetic-scene')
    assert store.health()['observation_count'] == count + 3
    sampler.tick(100)
    assert store.health()['observation_count'] == count + 3
    assert store.source_control('synthetic-scene')['sample_interval_seconds'] == 0
