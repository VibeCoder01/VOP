# Phase 5 — Observation stage timings (2 November 2026)

Owner authorised timing instrumentation to identify observation latency bottlenecks.
No camera/session/scheduling policy or model change; remain in Phase 5.

## Changes

- `src/vop/stage_timings.py`: monotonic local stage accumulation, immutable sample
  snapshots, successful-only median/nearest-rank 95th percentile; missing is not zero.
- `src/vop/pipeline.py`: measure engine readiness, acquisition, preparation (sum over
  preview and question mask/ROI groups), engine requests (sum over groups), save and
  total. Separate provider-reported elapsed time is nested within request time.
  Retain at most 100 completed/failed attempt metadata samples, protected by the
  existing preview lock. No images or credentials enter timing metadata.
- `src/vop/diagnostics.py`: passive per-camera latest/median/95% table and JSON metadata;
  filter to current engine ID, revision and synthetic identity. Retired/deleted cameras
  are absent. No history replay or new network requests on Diagnostics page loads.
- `tests/test_stage_timings.py`: deterministic fake-clock integration covering actual
  pipeline stages, persistence boundary, failed capture exclusion, percentile math,
  snapshot isolation and engine-revision separation. Existing diagnostics tests also
  verify passive routes and access controls.
- README/changelog/runbook and package version **0.6.12**.

## Validation

- `.venv\Scripts\python.exe -m pytest -q tests/test_stage_timings.py tests/test_diagnostics.py tests/test_phase1_service.py tests/test_phase1_config_storage.py tests/test_phase2_sampling_roi.py tests/test_camera_answer_groups.py tests/test_question_masks.py tests/test_observe_grid.py`:
  **98 passed in 33.76 seconds**, before final missing-provider/engine-identity guards.
- Final `.venv\Scripts\python.exe -m pytest -q tests/test_stage_timings.py tests/test_diagnostics.py`:
  **11 passed in 5.45 seconds**, including those guards and revision-filter assertion.
- `git diff --check`: passed.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.12**. `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- Authenticated managed restart: HTTP **202**, new instance **ready**; passive
  `/api/v1/diagnostics` confirmed timing metadata on all four cameras.

Existing owner-authorised monitoring then produced two successful samples. A passive
metadata snapshot showed Cat Cam acquisition 4427.0 ms, engine readiness 6639.0 ms,
provider 1999.9 ms, request 2234.9 ms and total 14431.4 ms. Living Room acquisition
4433.7 ms, readiness 124.9 ms, preparation 796.6 ms, request 607.2 ms, provider
286.4 ms, saving 1137.4 ms and total 7159.1 ms. These are initial observations, not a
controlled benchmark or claimed speedup. No extra camera capture/inference or
hardware test was manually requested. No imagery was viewed. Pinned model revision
remains `051bcc464b01b9f92942b364d9586b0ef5912432`; no new device/runtime validation,
model download, microphone/audio, Tapo action, email/SMS or GPU benchmark was run.
CI outcomes must be checked on the PR and later main push separately.

## Boundaries and next work

Timing samples reset at restart and share a global 100-attempt bound; slow cameras
can have fewer samples. New stored results include partial `stage_timings` marked
`boundary=before_save`; they cannot include their own save/commit time. Complete
save/total timings live in Diagnostics memory. Failed early attempts are shown as
incomplete_or_failed and never contribute to successful statistics. Inference failures
keep their result status; missing stages are unmeasured. Provider inference is not
added to request time. Synthetic test timings are not hardware evidence.

Total starts after the pipeline lock is acquired, includes uninstrumented local
bookkeeping, and ends after save and preview publication. Scheduler wait, camera-only
tests, browser display latency and later automation dispatch are not instrumented.
Early failed observations may include save time for their failure record. No extra
SQLite write, dependency or network endpoint was added. Existing history is unchanged.

Collect a representative sample before optimising. Persistent RTSP acquisition is
the strongest initial candidate; evaluate it within the authorised Phase 5 work.
Phase 6 remains unauthorised. No auto-merge.
