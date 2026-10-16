# Automatic Trends refresh — 16 October 2026

Changed `src/vop/dashboard.py`, `tests/test_trends_refresh.py`,
`tests/test_phase2_browser_storage.py`, `README.md`, `CHANGELOG.md` and this report.
Supports the existing Trends UI in the authorised Phase 4 pilot.

Trends loads an authenticated same-origin script that reloads its current URL every 10
seconds. The selected source, time zone and date range remain in that URL. The timer skips
hidden tabs, focused filters and changed filter values that have not been applied. Applying
filters starts a fresh page and timer. Keep a manual Refresh now link and no-JavaScript
guidance. Refresh only reads existing results; it does not start sampling, camera capture,
worker recovery or inference. Other pages do not load the timer script.

Windows commands/results:

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_trends_refresh.py tests/test_title_camera_names.py tests/test_observation_images_ui.py`:
  7 passed in 4.82 s.
- An initial full-suite run found the old no-JavaScript assertion for the Trends page. Update
  it to require exactly the local refresh script on Trends, no inline code, and no external
  assets. Preserve the no-script expectation on the other tested pages.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_phase2_browser_storage.py tests/test_trends_refresh.py`:
  13 passed in 6.03 s.
- `.\.venv\Scripts\python.exe -m pytest -q`: 305 passed, 4 skipped in 75.40 s. The skips
  are Linux-only helper tests on Windows.
- `.\.venv\Scripts\python.exe tools\phase2_smoke.py`: PASS; synthetic input, explicit mock,
  six browser-session views, replay, restricted image denial (403), deleted image denial (404)
  and 21 answers persisted after restart. No live cameras connected.
- `git diff --check`: passed.

The timer regression executes the actual JavaScript with Node and a minimal DOM/timer harness,
checking the 10-second period, reload, unchanged URL, hidden tab, focus, dirty values and missing
form. Node is an optional test runtime, not a server dependency; that one test skips if Node
is unavailable. Route tests verify authentication, viewer support, self-only CSP, no capture
and unchanged source controls. No new visual browser automation was performed.

Applied with the normal app restart endpoint. Fresh-instance health returned HTTP 200;
all 343 existing answers and enabled/image-saving/interval controls were preserved. No new
camera, model or GPU tests were requested for this UI change. No dependency, schema, model
revision or inference behavior changed. Historical approved d1 revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Limitations: automatic refresh needs JavaScript and a visible tab; unsaved filter edits pause
it until applied or reverted. Refresh does not enable monitoring, so new points require new
recorded observations. An already-open old Trends page must be refreshed once to load the
new script. Recommendation: review automatic updates in the current Phase 4 pilot using the
existing saved monitoring settings. Phase 5 remains unauthorised.
