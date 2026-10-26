# Phase 4 — delete questions while monitoring

Date: 26 October 2026

## Cause and change

Question deletion already waited off the event loop for browser admission, capture
and alert locks. However, its confirmation fingerprint included the full recorded
history. Every new observation invalidated it, so an actively monitored camera could
force repeated confirmations indefinitely.

- `src/vop/removal.py`: bind single/bulk confirmation to the selected question
  identities, specifications, policies, enabled state and related rule configuration.
  Recording or clearing data no longer invalidates confirmation. Re-read the latest
  deletion selection under the existing locks and SQLite transaction, so observations
  completed while waiting are included. Keep version/configuration checks, all-or-none
  selection validation, rollback, authorization, CSRF, audit and reserved question IDs.
- Clarify on the confirmation page that counts are a preview, new matching data is
  included, shared images/raw details are cleared, and the camera need not be paused.
  Remaining questions keep monitoring. Other history-only deletion is unchanged.
- `tests/test_removed_question_bulk.py`: test single and bulk deletion waiting for
  all three dependencies while health remains responsive; commit an explicit synthetic
  in-flight answer/image before the capture lock is released. Verify one confirmation
  succeeds, new images/answers are purged, controls are unchanged and a later capture
  cannot restore deleted questions. Configuration changes still force review.
- `tests/test_question_data_deletion.py`, `tests/test_removal.py`: retain missing/stale confirmation,
  permission and atomic rollback checks using configuration changes for staleness.
- `README.md`, `CHANGELOG.md`: describe the all-data confirmation scope and retain
  the distinct current-data checks for history-only deletion.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_removed_question_bulk.py tests/test_question_data_deletion.py`: **17 passed in 22.49s**.
- `.\.venv\Scripts\python.exe -m pytest -q`: **388 passed, 4 skipped, 1 failed in 170.29s**.
  The failure was an obsolete message assertion in `tests/test_removal.py`; update it
  to the configuration-change message, then rerun that permissions/CSRF guard.
  The four skips are opt-in hardware tests.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_removal.py::test_permanent_question_delete_permissions_csrf_and_active_guard`: **1 passed in 1.62s** after updating the message assertion.
- `git diff --check`: passed.
- Authenticated JSON managed restart: HTTP 202; new instance ready; all three source
  control tuples (enabled, evidence retention, interval) preserved. Observation count
  stayed at 33926 during restart verification. No live deletion request was submitted.

## Hardware, limits and next check

No live question/data deletion, camera connection, image inspection, model run,
GPU benchmark or model revision change was performed. All deletion tests used
explicit synthetic inputs and disposable databases. Historical approved Liquid
revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

An already-running capture/alert must finish before deletion; it is not cancelled.
Counts can increase before deletion, as the page now explains. Shared saved images
and raw engine data are cleared; other questions' normalized answers are retained.
Removing the last enabled question leaves camera controls intact but no further
question observations are scheduled until an active question is available.
Existing backups/exports are unchanged. The next Phase 4 acceptance check is a
user-selected question deletion during monitoring after refreshing the page; do not
perform unsolicited deletion of user records. Phase 5 remains unauthorised.
