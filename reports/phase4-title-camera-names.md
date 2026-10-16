# Title version and observation camera names — 16 October 2026

Changed `src/vop/dashboard.py`, `tests/test_title_camera_names.py`, `README.md`,
`CHANGELOG.md` and this report. Supports existing UI-003/UI-004 within Phase 4.

Show the installed VOP package version in a small, muted label beside VOP at the far left and
in browser-tab titles, including sign-in. Use Python's package metadata rather than a copied
version constant. Current project release remains 0.5.0; no release version is invented.

Use camera/input names in Individual Observations, recent observations, Continuous
Observations (Episodes), Trends, capture results and inspection. Resolve active/removed names and
stored configuration, with the stable ID as fallback. Keep IDs in URLs, stored records and
technical details. HTML components escape user-supplied names.

Commands and observed Windows results:

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observation_images_ui.py tests/test_ordinal_labels.py tests/test_separate_setup.py`:
  18 passed in 5.96 s.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_title_camera_names.py`: 1 passed in 1.61 s.
- `.\.venv\Scripts\python.exe -m pytest -q`: 303 passed, 4 skipped in 65.03 s. Skips are
  Linux-only helper tests on Windows.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_title_camera_names.py tests/test_phase2_browser_storage.py`:
  12 passed in 7.54 s after adding the sign-in version label.
- `.\.venv\Scripts\python.exe tools\phase2_smoke.py`: PASS; real loopback HTTP/browser
  sessions, six views, replay, retained synthetic image, viewer denial (403), deleted image
  denial (404), and 21 answers persisted after restart. Explicit mock, no live cameras.
- `git diff --check`: passed.

Applied with the normal authenticated browser restart endpoint. Fresh-instance health
returned HTTP 200, all 157 existing answers remained, and enabled/image-saving/interval
controls matched before and after. No real-camera test, GPU benchmark or model inference
was run. No model revision, dependency, schema or inference behavior changed; the existing
approved Liquid revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

No new visual browser automation was performed; generated HTML and synthetic browser routes
were checked offline. Names reflect current display names; technical provenance retains the
original IDs. Recommendation: review the small version label and named observation pages in
the current Phase 4 pilot. Phase 5 remains unauthorised.

Placement correction: moved the version from page headings into the far-left VOP brand link,
keeping it visible on narrow screens. Trends now uses the same name/ID fallback as observations.
The regression check parses brand/main placement and covers escaped Trends names and ID fallback.
`.\.venv\Scripts\python.exe -m pytest -q tests/test_title_camera_names.py tests/test_observation_images_ui.py tests/test_phase2_browser_storage.py`:
16 passed in 7.13 s. The Phase 2 synthetic browser/image smoke also passed again. No hardware
tests or user settings changed for this presentation correction.
