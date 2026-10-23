# Phase 4 — direct question deletion and faster counts

Date: 23 October 2026

## Cause and change

Questions rendered each Removed questions row by calling `question_selection`, which
loaded every associated run result, built a deletion fingerprint and queried other
answers/images separately for each run. The repeated unindexed run-ID scans grew
poorly as monitoring history accumulated. Opening this listing needs only counts.

- `src/vop/history_deletion.py`: add `question_counts`, four aggregate queries with
  no result/answer payloads or per-capture queries. Reuse it in the detailed preview
  while retaining answer sequences, run-result hashes, rules and event/alert IDs in
  the fingerprint. No deletion, retention or validation semantics changed.
- `src/vop/removal.py`: use count-only queries in the Removed questions list.
- `tests/test_question_counts.py`: verify fixed query count at 1 and 1,000 extra runs,
  exact all-version/shared counts, no payload reads and no full preview during listing.
- `README.md`, `CHANGELOG.md`, this report: behavior and evidence.

## Direct Delete question workflow

The user additionally requested removing the recoverable question-removal workflow.
Questions now has one compact list with direct Delete question actions and bulk
selection. Existing removed questions are included with deletion available and no
Restore action. Active questions can be deleted directly after confirmation. Old
Remove/Restore URLs open deletion confirmation without mutating configuration.
Camera removal/restoration remains recoverable and unchanged.

Deletion accepts active or legacy removed questions, waits for active work, validates
the complete snapshot after locking and performs the existing atomic data purge.
It disables the question, records the deletion tombstone and clears any old removal
marker. Definitions, reserved IDs, disabled alert-rule configuration and audit remain;
recorded answers, images, raw results, episodes and related notifications are purged.

Additional changed files: `src/vop/dashboard.py` uses the unified question list;
`src/vop/removal.py` implements the direct workflow and compatibility redirects;
`tests/test_removal.py`, `tests/test_question_data_deletion.py` and
`tests/test_removed_question_bulk.py` cover active deletion, legacy items, redirects,
access checks, queued work, atomic rollback and restart/backup persistence.

## Measurements and validation

Read-only local metadata benchmark against the configured saved database, with
approximately 24,539 observations and 14 removed question definitions:

- Old complete-preview loop for those definitions: **45.832 s**.
- New count-only loop for those definitions: **1.128 s**.

These measure the count workload, not a browser page navigation. Existing authorised
monitoring remained active, so the database was not a frozen benchmark snapshot.
No camera addresses, credentials, answer contents or image pixels were printed.

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_removed_question_bulk.py tests/test_question_data_deletion.py tests/test_removal.py`:
  24 passed in 31.84s.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_question_counts.py tests/test_removed_question_bulk.py tests/test_question_data_deletion.py`:
  19 passed in 31.94s.
- Before direct-deletion scope was added, `.\.venv\Scripts\python.exe -m pytest -q`:
  374 passed, 4 skipped in 133.99s (performance change only).
- Direct-deletion targeted checks: `.\.venv\Scripts\python.exe -m pytest -q tests/test_removal.py tests/test_removed_question_bulk.py tests/test_question_data_deletion.py tests/test_question_counts.py`:
  25 passed in 22.27s.
- Final `.\.venv\Scripts\python.exe -m pytest -q`: **373 passed, 4 skipped** in
  108.29s. The obsolete recoverable-question transition cases were replaced by
  direct deletion, old-link confirmation and legacy cleanup coverage.
- After adding the final Awaiting deletion label:
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_removed_question_bulk.py::test_legacy_removed_question_is_listed_only_for_deletion tests/test_question_counts.py`:
  **4 passed in 4.83s**.
- `git diff --check`: passed.
- Authenticated managed restart: HTTP 202; new instance ready, saved source controls
  preserved, observations 23476 -> 23478 during existing authorised monitoring.
- During implementation, tests caught FastHTML's unsupported stacked async route
  decorators. Replaced the old bulk-route alias with a normal 307 redirect; the final
  checks above verify the direct route. No coroutine responses remain.
- CI is tracked in this change's PR.

## Requested live cleanup

The user explicitly requested deleting all currently removed questions and data.
Read-only scoping found one not-yet-deleted question with 1,372 answers and no retained
images; 13 older deleted questions had zero remaining answers. No identifiers,
answers, credentials or pixels were printed. The proposed maintenance command would
stop VOP, revalidate the exact removed-only scope and purge it transactionally.
Automatic approval review rejected that command with "blocked by policy" and gave
no further reason. The command did not run: no shutdown or live deletion occurred.
Do not claim this cleanup completed or retry the rejected operation through another
path. The remaining question can be deleted with the app's new confirmation control.

## Limits and next acceptance

Tests use disposable synthetic histories. Real database access was read-only for
metadata/count measurements. No user data was changed/deleted by this work, no camera test,
model download, GPU benchmark or browser visual test was initiated. No dependency,
model or runtime changes. Historical approved model revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Count work still scales with history size and the number of removed questions; it
now uses a fixed four queries per question. Detailed deletion previews intentionally
still compute full fingerprints for safe confirmation. No persistent count cache or
schema migration was introduced.

Refresh Questions for Phase 4 acceptance. Phase 5 remains unauthorised. Do not auto-merge.
