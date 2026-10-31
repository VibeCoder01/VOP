# Observe camera grid — 31 October 2026

Observe now has Full view / Grid view choices above the camera filters. Each full
camera panel has a Grid View link beside monitoring/answers controls; each grid tile
can return to its full camera panel. Camera filters and Live / Last captured choices
are carried in URLs. The grid is responsive, with source names, privacy-masked images,
green monitoring or amber paused rings, and a three-lamp traffic light per question
inside the ring beside the image. Images retain hover/focus enlargement.

Question labels and exact answer text accompany colour. Binary Yes/No is green/red;
unknown, stale or disabled answers are amber. Ordinal colours describe lower/middle/
upper thirds of the configured numeric scale, retaining the fractional level text.
Choice shows the selected category, with green meaning a valid returned category.
No colour claims accuracy or desirability. Tooltips/accessible labels explain each
question; network failures mark received values stale with amber lights and a message.
Synthetic engines have the existing explicit demonstration warning.

The grid reuses the existing authenticated camera-answer, live-preview and processed
image endpoints. Its answer response has a separate ETag representation and monitoring
metadata. Last captured resolves the latest actual observation capture rather than a
later no-image Pause gap. A capture-deletion gap blocks older fallback. Missing or
deleted pixels never cause substitution of another retained frame. Last captured
starts no live decoder and remains useful while monitoring is paused.

Live previews retain the four-camera limit, privacy processing, CSRF lease request and
five-second renewal/15-second expiry. Grid leases are renewed only for monitoring
cameras in Live mode. Captured mode, paused cameras and hidden/closed pages do not
renew them. Metadata/image requests do not overlap for a card, image decoding has a
five-second bound, replacement pixels are decoded before display, and no automatic
page reload occurs. Questions poll once per second; live pictures up to five times
per second, independently of inference. Layout/image choices never alter monitoring,
sampling intervals, image retention or engine configuration. Viewer image restrictions
remain in place; no viewer image source/decoder requests are emitted.

## Files and validation

New `src/vop/observe_grid.py` and `tests/test_observe_grid.py`; shared dashboard and
browser script authorization; README, changelog, Phase 5 scope note, this report and
package version **0.6.11**. No dependency, schema or inference implementation change.

- `.venv\Scripts\python.exe -m pytest -q tests/test_observe_grid.py tests/test_observe_camera_selection.py tests/test_observe_answer_refresh.py tests/test_observe_image_pairs.py tests/test_ui_modes.py tests/test_phase2_browser_storage.py`:
  **38 passed in 27.19 seconds** before the final deleted-capture-gap refinement.
- `.venv\Scripts\python.exe -m pytest -q`: **524 passed, 6 skipped in 236.69
  seconds**, before that final refinement. Skips are four Linux-only remote-helper
  tests and two Linux Secret Service contracts on Windows.
- Final `.venv\Scripts\python.exe -m pytest -q tests/test_observe_grid.py tests/test_history_deletion.py tests/test_observe_image_pairs.py`:
  **27 passed in 16.18 seconds**, including actual capture deletion, preserved Pause
  images, no older retained fallback, live/captured resource isolation, permission
  checks, labels/colours, filter links and fake-DOM polling/decoding contracts.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`:
  installed **0.6.11**; `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `git diff --check` passed. Managed restarts returned **HTTP 202**, new instances
  **ready**, all three sources' monitoring/retention/capture-interval controls unchanged.
- `.venv\Scripts\python.exe tools/audit_deletions.py --check-vault`: **PASS**, zero
  issues in all 17 DB checks, zero pending cleanup or unused canonical/legacy files.
- Final CI status is recorded on the PR. PR checks and any later merged-main push
  are distinct results; passing results are never presumed.

No live browser visual/imagery inspection, manual camera/model/GPU, microphone, Tapo,
audio, email/SMS or benchmark test was run. All test frames were synthetic. Existing
authorised monitoring may continue; no source/action/automation was added to live
configuration. Model revision and hardware measurements are unchanged. Four simultaneous
live previews remain the limit; use Last captured for larger grids. Unsaved images can
leave memory and become unavailable. Existing temporal replay costs remain unchanged.
Remain in Phase 5 and validate the display with normal owner use. Phase 6 is not
started; no auto-merge.
