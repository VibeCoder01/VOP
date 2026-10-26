# Phase 4 — question deletion progress dialog

Date: 26 October 2026

## Changes and files

- `src/vop/removal.py`: add a native dialog to confirmed single and bulk question
  deletion forms. An indeterminate HTML progress bar and plain wait message explain
  that VOP can be waiting for an observation and that large histories take time.
  The small, self-hosted `/ui/question-delete.js` enhancement shows the modal on
  submit, preserves native POST/CSRF/result navigation, prevents duplicate submissions
  and prevents Escape from hiding an active operation. Back/forward-cache restoration
  closes the old dialog and restores submit labels. Normal initial page-show events
  do not interrupt an operation. Browsers without dialog support retain native forms;
  no-JavaScript instructions explain the wait.
- `src/vop/dashboard.py`: restrained responsive dialog, backdrop and progress styles.
- `tests/test_question_delete_progress.py`: single/bulk markup and native completion
  on disposable histories; auth on the script; Node event checks for submit, duplicate
  blocking, Escape, Back restoration and the unsupported-dialog fallback.
- `README.md`, `CHANGELOG.md`: explain the progress indicator and fallback.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_removed_question_bulk.py tests/test_question_data_deletion.py`: **17 passed in 22.20s**.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_question_delete_progress.py`: **3 passed in 5.15s** before the additional initial-page-show safeguard; included again in the full suite below.
- `.\.venv\Scripts\python.exe -m pytest -q`: **392 passed, 4 skipped in 161.16s**.
  Skips are the opt-in hardware tests.
- `git diff --check`: passed.
- Authenticated JSON managed restart returned HTTP 503 `storage_unavailable`.
  Read-only health reported ready but in-flight, with observation count 33926.
  The current database operation was left running; no process was forcibly stopped.
  Updated UI activation awaits a safe restart after that operation finishes.

## Limits and next check

The bar is intentionally indeterminate. It does not claim a measured percentage or
remaining time: deletion is one database transaction, and apparent per-question
completion would not mean the transaction has committed. The dialog stays until
the native request navigates to the result, error or updated confirmation page.
No background job service, polling endpoint or new dependency is introduced.
The database deletion/confirmation/rollback paths are unchanged.

No live user data deletion, real camera test, model run, GPU benchmark or browser
visual inspection was performed. All deletion tests use explicit synthetic data and
disposable databases. Historical Liquid model revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`; no hardware/model changes were made.
The next Phase 4 acceptance check is for the user to refresh Questions and confirm
an intended deletion, observe the popup and final result. Phase 5 remains unauthorised;
do not auto-merge or delete user records merely to demonstrate progress.
