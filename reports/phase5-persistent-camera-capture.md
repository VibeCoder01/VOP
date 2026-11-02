# Phase 5 — Optional persistent RTSP acquisition (2 November 2026)

Owner authorised the camera-acquisition optimisation, then specified optional and on
by default. No model, engine session or scheduling policy change; remain in Phase 5.

## Changes

- `inputs/persistent.py`: maximum four spawned, isolated RTSP workers. Destination
  policy is checked before opening/reusing a connection. A reader drains frames
  continuously and grabs a new full-resolution frame after each capture command.
  Only requested frames are retrieved/converted and PNG-encoded; idle frames are
  grabbed and discarded without pixel conversion.
  No old result/preview frame is used. Full-size PNGs enter the existing privacy,
  include/exclude and ROI preprocessing path, not browser routes directly.
- Connection cleanup: pause, disable, no enabled questions, edit/remove, dead worker,
  capture error/deadline and shutdown. A housekeeping check failure releases all
  connections. A failed attempt reports an error; the next scheduled attempt can
  reconnect. Existing retry/backoff applies, not silent stale-image fallback.
- `pipeline.py`, `service.py`: route RTSP monitoring through the pool and stop it
  during normal application shutdown. Preserve USB/one-shot/source consent paths.
  Beyond the pool's four connections, use the previous one-shot acquisition.
- `integration_ui.py`, `config.py`: per-camera **Keep camera connection open while
  monitoring**, checked by default for new and existing RTSP cameras; false survives
  saved profile restoration. Strict boolean config validation. USB has no such switch.
- `live_preview.py`: a mask grab releases the observation connection before its
  one-shot capture. Camera connection tests do the same, avoiding another competing
  RTSP client. Existing live previews remain separate, with their own four-camera cap.
- `tests/test_persistent_capture.py`, `tests/test_unified_camera_settings.py`: offline
  fake decoder/worker coverage for opening once, reading after requests, discarding
  intermediate frames, unique frame IDs, bounded capacity, opt-out, pause/edit/delete,
  reconnect after failure, shutdown, initial checkbox state and persisted opt-out.
- README/changelog/version **0.6.13**. No new dependencies or stored raw frame data.

## Validation

- `.venv\Scripts\python.exe -m pytest -q tests/test_persistent_capture.py tests/test_unified_camera_settings.py tests/test_stage_timings.py tests/test_live_previews.py tests/test_camera_save_queue.py tests/test_phase2_sampling_roi.py`:
  **31 passed in 13.48 seconds**, before the final test-release and dead-worker guards.
- Final `.venv\Scripts\python.exe -m pytest -q tests/test_persistent_capture.py tests/test_unified_camera_settings.py tests/test_live_previews.py tests/test_camera_save_queue.py tests/test_question_masks.py tests/test_phase3_release.py`:
  **62 passed in 39.59 seconds**, including those guards and checkbox persistence test.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.13**. `.venv\Scripts\python.exe -m pip check`: no broken requirements.

- `.venv\Scripts\python.exe -m pytest -q`: **532 passed, 6 skipped in 246.66 seconds**,
  before the final grab/retrieve refinement; final decoder/connection-test guards
  and lazy pixel conversion are covered by the focused run recorded below.
  Skips are the existing Linux-only remote/helper and Secret Service contracts on Windows.
- `git diff --check`: passed.

- Final post-refinement repeat of the same 62-test focused command:
  **62 passed in 41.51 seconds**, covering grab/retrieve on-demand conversion.
- Managed restarts: HTTP **202**, new instance **ready**; first restart verified
  monitoring, image-retention and interval metadata unchanged.

## Before/after observation evidence

Passive pre-change metadata at 20:33:19 UTC, successful samples in the current
100-attempt window:

| Camera | Samples | Acquisition median ms | Total median ms |
|---|---:|---:|---:|
| Cat Cam | 9 | 3751.4 | 4819.2 |
| Living Room | 36 | 3640.6 | 6004.4 |
| Front of House | 36 | 3649.1 | 6036.2 |
| Outhouse | 15 | 3521.7 | 4185.9 |

Post-change passive metadata at **20:42:31 UTC**, final grab/retrieve implementation.
All 39 recorded attempts succeeded; no current camera error. First startup attempts
are included, not removed from the sample. Each camera had at least one reused
connection; the slower-scheduled camera sample is still small.

| Camera | Successful samples | Acquisition median ms | Total median ms | Total reduction vs before |
|---|---:|---:|---:|---:|
| Cat Cam | 3 | 537.5 | 2172.0 | 54.9% |
| Living Room | 12 | 325.0 | 3393.6 | 43.5% |
| Front of House | 20 | 305.0 | 3314.6 | 45.1% |
| Outhouse | 4 | 371.5 | 1017.9 | 75.7% |

Acquisition fell by approximately 86–92%. Total-stage medians are independent and
need not sum. Typical preparation still took 174.6–1028.6 ms and saving 14.3–1504.1 ms;
those paths were not optimised in this change. Existing inference median remained
236.1–504.3 ms. The comparison is ordinary live monitoring on a shared laptop, not a
controlled benchmark or long-duration reliability/accuracy test. CPU snapshots were
also taken: VOP processes used 46.1% of host capacity with the initial read/discard
implementation, and 28.5% with final grab/retrieve, while host CPU was 67.9% and 71.3%
respectively. These one-second, differing-load snapshots are resource observations,
not a measured CPU speedup claim. No camera images were inspected.

The observed latency improvement meets the intended goal. Leave persistent capture
on by default, with the per-camera opt-out for resource/connection constraints, and
stop this optimisation work as requested. Future tuning is not needed for this scope.

## Limits / recommendation

Initial connection/startup still takes time. The reader drains decoded frames, but
camera/network/backend buffering can still add sensor-to-answer delay. A newly read
frame is not a guarantee of zero camera buffering. Background decoding uses laptop
CPU/bandwidth and cameras may impose client limits; switch off per camera if needed.
Four persistent observations plus up to four live previews can use eight connections
across four cameras. No shared-decoder or incremental episode-processing redesign was
included. Scheduling remains serial, so one-second targets across cameras are not
promised. Persisted stage timings are partial before-save; Diagnostics is complete.

No imagery was viewed, no model downloaded, and no new GPU benchmark, model/runtime
validation, USB hardware, audio/microphone, light/hub, email or SMS action was requested.
The existing pinned model remains `051bcc464b01b9f92942b364d9586b0ef5912432`. Owner-authorised
scheduled monitoring supplies the live comparison; no additional manual camera or
inference request is needed. CI results must be checked on the PR and later main
push separately; none is presumed. Stop after this optimisation if representative
monitoring confirms the improvement. Phase 6 is not started; no auto-merge.
