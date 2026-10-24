# Phase 4 — Trends camera buttons

Date: 24 October 2026

## Change and files

- `src/vop/dashboard.py`: use the shared multi-select camera-name buttons on Trends.
  All cameras resets selection. Buttons retain applied From/Through dates. The date
  form carries every selected source in hidden fields; Apply dates preserves them.
  Use workspace timezone and ignore obsolete UI timezone query parameters. Keep
  valid date parsing, date-range semantics and auto-refresh. Summary replay accepts
  a selected set and skips unselected cameras before querying history.
- `tests/test_trends_camera_buttons.py`: three synthetic camera definitions verify
  multi-selection, reset/deselection, date preservation in both directions, configured
  timezone, invalid source/date handling, scoped replay and unchanged source controls.
- `tests/test_trends_refresh.py`: exercise the existing refresh guard with repeated
  source parameters and dates; preserve hidden-tab/focus/unsaved-change behavior.
- `tests/test_phase2_browser_storage.py`: obsolete invalid UI timezone fields are
  now ignored on Trends, rather than rejected. External-asset safeguards remain.
- `README.md`, `CHANGELOG.md`, this report: usage and validation evidence.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_trends_refresh.py tests/test_phase2_controls.py tests/test_observe_camera_selection.py tests/test_history_camera_buttons.py`:
  22 passed in 20.80s.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_trends_camera_buttons.py tests/test_trends_refresh.py tests/test_phase2_browser_storage.py::test_all_views_native_markup_and_no_external_assets`:
  4 passed in 3.59s.
- `.\.venv\Scripts\python.exe -m pytest -q`: **380 passed, 4 skipped** in 149.34s.
- `git diff --check`: passed.
- Authenticated managed restart: HTTP 202; new instance ready, source monitoring/
  evidence/interval settings preserved. Observations 27288 -> 27292 while existing
  authorised monitoring drained/resumed. No deletion was submitted.
- CI is tracked in this change's PR.

## Limits and next acceptance

Tests use synthetic/offline data. No new camera connection, model download, GPU run,
user-data deletion or browser visual test was initiated. No model/runtime changes;
historical approved revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Camera buttons preserve applied dates; unsaved date edits must be applied before
changing cameras. Selection is URL-based and selecting the last selected camera
again resets to All cameras, consistent with Observe/history. Existing source names
are used; retired cameras have no button. API/export timezone options remain available.

Refresh Trends for Phase 4 acceptance. Phase 5 remains unauthorised. Do not auto-merge.
