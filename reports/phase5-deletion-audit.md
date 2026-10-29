# Phase 5 deletion lifecycle audit — 29 October 2026

## Live read-only result

`.venv\Scripts\python.exe tools/audit_deletions.py --check-vault` returned **PASS**.
Every database issue counter was **0**, pending secret cleanup **0**, unused canonical
vault filenames **0**, and unused known legacy vault filenames **0**. No checks were
skipped. The tool used SQLite read-only/query-only mode and vault filenames, without
decrypting credentials, loading imagery, connecting to hardware or deleting live records.
This is a snapshot of this configured workspace, not a sweep of unknown external copies.

Checked ownership includes source/question versions and controls, frames/runs, observations,
episodes, alert/delivery/rule state, stored test answers, action audio, automation action
references, waiting jobs, SQLite foreign keys and protected-setting references. Camera
removal is recoverable retirement. Activity entries own complete historical snapshots;
reserved IDs, immutable revisions and disabled rules/automations awaiting reassignment are
intentional records. Backups, exports and independent model files/workers remain owned
outside a deleted configuration. See [deletion rules](../docs/deletion.md).

## Deletion-path gaps fixed

- Previously, deleting actions or inactive engine profiles left their protected keys.
  Explicit cleanup candidates now commit with deletion, then retry durably after failures
  or restart. Current/saved/retired/fallback/shared references and the dashboard key stay.
  A sending action keeps its account until it finishes; historical snapshots need no key.
- Windows cleanup also removes known recoverable legacy copies. Linux verifies absence
  after Secret Service clearing, including already absent values and locked matches.
  Only explicit candidates are processed; no automatic global vault sweep was added.
- Cleanup processes one candidate per pass, rotates blocked candidates, never holds a
  database writer transaction across OS-vault operations, and backs off 30 seconds after
  failures. Empty cleanup does not reserve the capture worker. Pending failures appear
  through the existing Actions/Diagnostics error reporting.
- Whole-input history deletion now includes empty captures and unreferenced saved frames.
  Question data deletion also erases stored test answers. Data deletion and retirement
  invalidate relevant preview and action-summary caches.

Changed files: `src/vop/actions.py`, `history_deletion.py`, `integration_ui.py`, `removal.py`,
`secrets.py`; new `secret_cleanup.py`, `deletion_audit.py`, `tools/audit_deletions.py`;
regressions in deletion/history/action/secret fixtures; README, deletion runbook, changelog
and package version **0.6.5**. No dependency or database schema migration was added.

## Validation

- Initial `.venv\Scripts\python.exe -m pytest -q`: **467 passed, 4 skipped, 1 failed**
  in 233.44 seconds. The first cleanup implementation briefly reserved capture when its
  queue was empty, causing an overload response in a source-settings test. Fixed with a
  no-work guard before acquiring the capture lock and a dedicated regression assertion.
- Final `.venv\Scripts\python.exe -m pytest tests/test_deletion_cleanup.py tests/test_history_deletion.py tests/test_question_data_deletion.py tests/test_removed_question_bulk.py tests/test_actions.py tests/test_secret_migration.py tests/test_phase1_service.py -q`:
  **89 passed, 2 skipped** in 58.78 seconds. Skips are Linux Secret Service command
  contracts on Windows. The full suite's four Windows skips were Linux-only remote-helper
  tests; none is evidence of a hardware test.
- Tests cover unshared/shared/sending accounts, restart retry, transaction rollback,
  dashboard-key protection, database-writer availability during OS cleanup, no-work
  scheduler access, Windows legacy resurrection, Linux command contracts, complete history
  purge including empty captures, retained other-question answers and read-only detection.
- `git diff --check`: passed. Full Windows/Ubuntu push and PR CI results will be recorded
  on the pull request after push; they are not presumed here.

No live entity deletion, model benchmark, camera/device probe, audio playback or email/SMS
delivery was manually tested. Existing authorized monitoring may continue. OS-vault
unavailability delays cleanup visibly; an action already sending can finish and messages
already delivered cannot be withdrawn. Unknown external configuration references are outside
this workspace audit. No new model revision or performance claim is made. Recommendation:
continue Phase 5 normal use and owner acceptance; Phase 6 is not started. No auto-merge.
