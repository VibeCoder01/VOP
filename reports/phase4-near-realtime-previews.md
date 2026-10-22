# Phase 4: near-real-time Observe previews

22 October 2026. The owner requested camera images as near real-time as possible.
This extends the Phase 4 foreground viewing workflow, not Phase 5 deployment.

## Implementation and changed files

- `src/vop/live_preview.py`: one supervised persistent decoder per viewed RTSP/USB
  source, maximum four active sources. Continuously drain incoming frames and replace
  the latest pixels; publish privacy-masked 960 × 540 JPEG previews at a target 5 fps.
  A dedicated publisher avoids building a decoder backlog while encoding. Use existing
  protected camera endpoint/credential policy; suppress native diagnostics containing
  credentials. Kill stalled children and reconnect with 2–30 second bounded backoff.
  A 15-second lease closes connections after the last visible-page renewal. Multiple
  tabs coalesce onto one decoder per camera. No model calls or database image writes.
- `dashboard.py`, `browser_auth.py`: operator-only, origin/CSRF-protected preview
  keepalive requests in View mode, independent of the inference admission lock. Browser
  checks latest-frame metadata every 0.2 seconds in parallel across cameras and renews
  leases every 5 seconds while visible. Download changed images only; show connecting,
  reconnecting, missing-details and capacity messages. JPEG/PNG types and capture times
  remain explicit. Green/amber rings continue to describe question monitoring, not
  whether the preview decoder is active.
- `service.py`, `pipeline.py`: attach the preview manager and close all children on
  app shutdown/restart. Keep inference cadence and deployment-neutral frame interfaces.
  Release exclusive USB devices during observation acquisition, then resume previews.
  Existing camera controls, saved engine configuration and evidence policy are unchanged.
- `inputs/sources.py`: share validated protected camera locator construction between
  one-shot and persistent acquisition. No credentials are added to public configuration.
- `preprocessing.py`: share the same source privacy-mask operation between inference,
  saved stills and live previews; masks precede resizing/JPEG encoding.
- `integration_ui.py`: camera setup changes clear the old preview and reconnect backoff.
- `tests/test_live_previews.py`: persistent decoder opening once, continuous draining,
  masks, leases, stalls/retries, configuration changes, bounds, USB exclusivity, role/
  origin/CSRF checks, capture/inference independence and no recorded observations/images.
- `tests/test_observe_image_refresh.py`: faster refresh, visible-only lease renewal,
  coalescing renewals and hidden-tab pause in the Node browser-script harness.
- `tools/preview_smoke.py`: actual spawned producer/IPC/termination with explicitly
  synthetic pixels, without OpenCV, camera access or model weights.
- `.github/workflows/offline-tests.yml`, `tools/build_release.py`: run the synthetic
  preview process smoke check on Windows/Linux and include it in the portable release.
- README, CHANGELOG and CODEX_PHASE_4_PLAN document the workflow, authorisation and limits.

OpenCV's FFmpeg open/read timeout settings are configured when opening the connection;
CAP_PROP_BUFFERSIZE is a backend-dependent hint, supplemented by continuous draining.
See the [official OpenCV 4.13 video I/O documentation](https://docs.opencv.org/4.13.0/d4/d15/group__videoio__flags__base.html).

## Commands and observed results

- `.\.venv\Scripts\python.exe -m compileall -q src/vop`: passed.
- Initial preview/image/sampling regression command: 12 passed in 3.46s.
- `.\.venv\Scripts\python.exe -m pytest -q`: 345 passed, 4 skipped in 66.89s
  before the final USB-exclusive-device regression was added.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_live_previews.py tests/test_observe_image_refresh.py tests/test_phase2_sampling_roi.py`:
  14 passed in 3.00s, including USB release/resume behavior.
- Final camera setup and permission regression command:
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_live_previews.py tests/test_phase4_worker.py tests/test_metric_help_camera_names.py tests/test_observe_image_refresh.py`:
  40 passed in 12.39s.
- `.\.venv\Scripts\python.exe tools/preview_smoke.py`: PASS twice. Five
  distinct explicit synthetic frames received over one spawned producer connection;
  masked pixels verified, inference slot held throughout, expired lease closed child.
  Cameras not connected; weights not loaded.
- `.\.venv\Scripts\python.exe tools/phase4_smoke.py`: PASS. Explicit mock
  worker over actual loopback HTTP, three synthetic observations persisted after
  restart, disconnection behavior and real Windows DPAPI checked. No cameras/weights.
- Read-only local OpenCV check: 4.13.0, FFmpeg available, both open/read timeout
  constants available. No camera was opened by this check.
- `git diff --check`: passed.

## Actual application and limits

Applied through authenticated managed restart: HTTP 202 and a new instance; camera
monitoring/evidence/interval settings preserved, observations 7359 -> 7362 while
existing monitoring drained/resumed. Opening or refreshing Observe starts the new
transient feeds. No new live-camera test, model download or GPU benchmark was
initiated during implementation. No model/runtime was changed. Historical approved
revision remains 051bcc464b01b9f92942b364d9586b0ef5912432.

The target 5 fps and 0.2-second browser checks are software settings, not measured
camera-to-screen latency. Real RTSP image freshness, frame rate and laptop CPU use
remain manual acceptance checks; camera encoding and network delay can add latency.
Previews use a separate RTSP connection from sampled inference. USB previews pause
briefly while observations acquire the device. Four previews can run concurrently;
other input types retain the sampled-still path. Hidden/closed tabs can retain a
camera lease for up to 15 seconds after their last renewal. Preview frames stay in
memory only; they are not recorded as answers or saved evidence. Model sampling,
events, trends, alerts and GPU workload/session policy are unchanged.

Continue Phase 4 manual acceptance of the existing Tapo cameras in Observe. Phase 5
remains unauthorised. Do not auto-merge.
