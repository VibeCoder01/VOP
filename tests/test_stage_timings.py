"""Synthetic deterministic clock tests; no real cameras, SSH or GPU."""
from types import SimpleNamespace
from dataclasses import replace

from test_removed_question_bulk import app, no_workers, SID
from vop.contracts import ProviderError
from vop.inputs.sources import capture_inline
from vop.stage_timings import StageTimings, summarise
from vop.diagnostics import snapshot


def test_pipeline_measures_local_stages_and_persists_pre_save_boundary(app, monkeypatch):
    import vop.pipeline as module
    clock = [0.0]
    monkeypatch.setattr('vop.stage_timings.perf_counter', lambda: clock[0])
    pipeline = app.state.pipeline
    frame = capture_inline(pipeline.sources[SID])
    def advance(seconds, result=None):
        clock[0] += seconds
        return result
    pipeline.auto_worker = SimpleNamespace(ensure_ready=lambda: advance(2), last_failure=None)
    monkeypatch.setattr(pipeline.capture_adapter, 'capture', lambda source: advance(3, frame))
    prepare, infer, save = module.preprocess, module.infer, pipeline.store.save
    monkeypatch.setattr(module, 'preprocess', lambda *a, **kw: advance(.5, prepare(*a, **kw)))
    monkeypatch.setattr(module, 'infer', lambda *a: advance(.25, replace(infer(*a), elapsed_ms=125)))
    monkeypatch.setattr(pipeline.store, 'save', lambda *a, **kw: advance(4, save(*a, **kw)))
    pipeline.run(SID)
    sample = pipeline.timing_samples[-1]
    assert sample['stages_ms'] == {'engine_ready': 2000, 'capture': 3000,
                                    'prepare_image': 1000, 'engine_request': 250, 'save': 4000}
    assert sample['total_ms'] == 10250 and sample['provider_ms'] == 125
    assert sample['status'] == 'success'
    persisted = pipeline.store.previous(SID, frame.frame_id)['result']['stage_timings']
    assert 'save' not in persisted['stages_ms'] and persisted['total_ms'] == 6250
    data = snapshot(app)['cameras'][0]['timings']
    assert data['successes'] == 1 and data['rows'][-2]['latest_ms'] == 10250
    monkeypatch.setattr(pipeline.engine, 'engine_version', 'different-revision')
    assert snapshot(app)['cameras'][0]['timings']['attempts'] == 0


def test_failed_capture_is_timed_but_not_counted_as_success(app, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('vop.stage_timings.perf_counter', lambda: clock[0])
    def fail(source):
        clock[0] += 7
        raise ProviderError('capture_timeout', 'Synthetic timeout')
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', fail)
    app.state.pipeline.run(SID)
    sample = app.state.pipeline.timing_samples[-1]
    assert sample['stages_ms'] == {'capture': 7000, 'save': 0}
    report = summarise([sample])
    assert report['successes'] == 0 and report['rows'][1]['latest_ms'] == 7000
    assert all(row['median_ms'] is None for row in report['rows'])


def test_stage_accumulation_percentiles_and_snapshot_isolation(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr('vop.stage_timings.perf_counter', lambda: clock[0])
    trace = StageTimings('synthetic')
    with trace.stage('prepare_image'): clock[0] += .1
    old = trace.snapshot()
    with trace.stage('prepare_image'): clock[0] += .2
    assert old['stages_ms']['prepare_image'] == 100
    assert round(trace.snapshot()['stages_ms']['prepare_image']) == 300
    samples = [dict(old, status='success', total_ms=n) for n in range(1, 21)]
    row = summarise(samples)['rows'][-2]
    assert row['median_ms'] == 10.5 and row['p95_ms'] == 19
