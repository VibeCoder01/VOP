# Phase 4 — Episodes name, camera counts and timeline

Date: 26 October 2026

## Design and changed files

Visual thesis: retain the calm white workspace, with blue sampled intervals and
amber gaps. Content plan: counted camera filters, one dominant timeline, then the
existing detail table. Interaction thesis: native scrolling with pinned context,
centred zoom/Fit, and hover/keyboard inspection without page reloads.

- `src/vop/episodes_ui.py`: pure server-rendered SVG and a small local script. One
  lane per camera/question/version avoids overlapping different questions. Merge
  adjacent recorded segments in one pass; preserve unknown gaps and point-only
  starts. Open episodes never extend to the current time. The date axis uses the
  workspace timezone. Native scrolling supports horizontal/vertical movement;
  labels and axis stay visible. Zoom is bounded to 1–64×, with slider, +/- and Fit;
  redraw timestamps only for the visible width. Clickable/focusable episode shapes
  link to the first recorded observation. No inline script/style or new dependency.
- `src/vop/dashboard.py`: rename navigation, heading and browser title to
  **Episodes (Contiguous active observations)**. Add all-time count badges to the
  existing multi-select camera buttons on this page only. Load at most 1,000 selected
  episodes for the timeline and retain 100 detail rows. Batch-fetch matching
  immutable question names in groups of 300 keys (900 bound parameters), rather
  than selecting every historical specification or querying per event. Resolve
  camera names once per distinct camera. Add responsive, restrained chart styles.
- `src/vop/storage.py`: one grouped event-count query for camera buttons.
- `src/vop/browser_auth.py`: allow the authenticated timeline script in View mode;
  authentication and configuration mutation rules remain unchanged.
- `tests/test_episodes_timeline.py`: synthetic multi-camera count/selection/scope,
  literal-text escaping, recorded segment/gap merging, no extrapolation and empty
  state. A Node fake-DOM check exercises zoom bounds, centre preservation, Fit,
  resize, pinned labels, bounded axis work and scroll-frame coalescing; no fetch.
- `tests/test_history_camera_buttons.py`, `tests/test_observation_images_ui.py`:
  update the requested name and preserve existing filter/mode assertions.
- `tests/test_phase2_browser_storage.py`: retain the no-inline/no-external-assets
  check while recognizing the new self-hosted Episodes script.
- `README.md`, `CHANGELOG.md`, this report: scope and operation.

## Validation

- `.\.venv\Scripts\python.exe -m compileall -q src/vop`: passed.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_episodes_timeline.py tests/test_history_camera_buttons.py tests/test_observation_images_ui.py`:
  **10 passed in 17.85s**, before narrowing question-name reads to matching keys.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_episodes_timeline.py`:
  **3 passed in 6.07s** after that query change.
- `.\.venv\Scripts\python.exe -m pytest -q`: **408 passed, 4 skipped, 1 failed in
  177.14s**. The failure was the old assertion that Episodes has no script; update
  its expected local asset without relaxing the inline/external-code guard.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_phase2_browser_storage.py::test_all_views_native_markup_and_no_external_assets`:
  **1 passed in 0.96s** after updating that expectation. Skips in the full suite
  were the opt-in hardware tests.
- `git diff --check`: passed.
- Safe activation: two idle authenticated JSON health checks, managed restart HTTP
  **202**, new instance ready; all three source-control tuples preserved and
  observation count **16477 → 16477** during verification. No live episode/camera
  page was read for visual inspection and no capture request was submitted.

## Limits, hardware and next check

Counts cover all recorded episodes and do not shrink when the local zoom changes.
The timeline displays the newest 1,000 selected episodes, not unlimited history;
the page explains this. All cameras preserves the existing access to retired-camera
history, while retired cameras remain absent from selection buttons. The view is a
snapshot; refreshing loads new observations without starting capture. Without
JavaScript, native scrolling and the static SVG/links remain, but zoom/pinning need
the script. Extremely long labels are shortened on lanes with full text in titles.

This rename does not change episode measurement semantics. A configured resume
policy can keep an episode across an unknown gap; that gap is visibly dashed and
excluded from active-time bars. Point-only legacy events are not drawn as invented
continuous durations. Visual browser/screenshot QA was not performed; route and
synthetic DOM/script behavior were checked offline.

No live data was deleted and no real camera/model/GPU test or download was run.
Historical Liquid revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.
Keep the existing Phase 4 hardware separation. Next acceptance: refresh Episodes in
View mode, select cameras and inspect zoom/scroll and gap rendering on intended
user data. Phase 5 remains unauthorised; do not auto-merge.
