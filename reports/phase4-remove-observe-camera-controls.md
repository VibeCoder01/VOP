# Phase 4 — removal waits and camera display controls

Date: 23 October 2026

## Change and files

- `src/vop/removal.py`: recoverable question/camera remove and restore now wait for
  observation and alert locks. All callers use a worker thread; the event loop stays
  responsive. Existing item validation runs after acquiring locks. Intentional gap
  records, disabled alert rules, preserved history and restore semantics remain.
- `src/vop/browser_auth.py`: include remove/restore routes in waitable admission,
  after authentication, origin, CSRF and Configure mode checks.
- `src/vop/dashboard.py`: Observe camera-name buttons toggle multiple source query
  parameters. All cameras clears the selection. Cards, answers and summary totals
  follow the selection; Refresh view preserves it. Observe ignores obsolete timezone
  and date query fields and uses the configured workspace timezone. Other pages keep
  their timezone controls. Compact CSS is scoped to the Camera setup list.
- `src/vop/integration_ui.py`: matching Edit button and camera-list styling hook.
- `tests/test_removed_question_bulk.py`: real-lock contention tests for remove/restore
  on questions and sources; verify waits, responsive health reads and retained history.
- `tests/test_removal.py`: retain access/CSRF checks, replace obsolete busy rejection.
- `tests/test_observe_camera_selection.py`: offline three-source selection, deselection,
  reset, invalid source, refresh, totals, unchanged controls and camera action markup.
- `README.md`, `CHANGELOG.md`, this report: usage and validation.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_removed_question_bulk.py tests/test_removal.py tests/test_observe_camera_selection.py tests/test_separate_setup.py tests/test_ui_modes.py`:
  **32 passed in 32.00s**.
- The first targeted run found test expectations that did not account for existing
  intentional gap records and enabled fixture defaults. Corrected the expectations;
  no production behavior was changed to suppress those records or alter those defaults.
- `.\.venv\Scripts\python.exe -m pytest -q`: **371 passed, 4 skipped** in 112.73s.
- `git diff --check`: passed.
- Authenticated managed `POST /ui/restart`: HTTP 202; new instance ready, camera
  enabled/evidence/interval controls preserved. Observations 23672 -> 23678 while
  existing monitoring drained/resumed. No removal/deletion was submitted to the user app.
- CI is tracked in the PR for this change.

## Limits and next acceptance

Tests use disposable synthetic sources, histories and camera credentials. No real
user item was removed/restored/deleted, no camera test or new model/GPU test was
initiated, and no browser visual test was run. No dependency or model changes.
Historical approved model revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Waits are request-scoped; keep the page open. Observe selection lives in the URL,
changes display only and resets when using a navigation link without source filters.
Selecting the last selected camera again resets to All cameras. Time display uses the
configured workspace timezone. Existing authorised monitoring can continue through
managed restart. New hardware measurements are not claimed.

Refresh Questions, Observe and Cameras for Phase 4 acceptance. Phase 5 remains
unauthorised. Do not auto-merge.
