# Phase 4 — efficient question deletion and pending dialog activation

Date: 26 October 2026

## Diagnosis and changed files

A read-only live query plan showed capture-run lookups scanning the observations
index/table (`WHERE run_id=?`). Existing lookup keys began with source ID, which
these queries did not supply. Every shared capture cleanup repeated these scans;
foreign-key checks when deleting runs had the same missing lookup.

- `src/vop/storage.py`: idempotently create `observations_run ON observations(run_id)`
  for new and reopened databases. This shared index covers cleanup, single-capture
  history deletion and the referencing foreign-key checks. No schema-version bump,
  model dependency or replacement database is required. Apply only on safe startup.
- `src/vop/history_deletion.py`: let question selections omit run payloads for
  confirmation. Remove the unused recorded-history hash, answer sequence loading
  and event-ID loading from question selections. Keep rule/identity confirmation
  in removal.py, counts and current per-question run results when deleting. Skip
  updates to frames whose image is already NULL.
- `src/vop/removal.py`: use the metadata-only selection for the confirmation snapshot.
  Deletion still reads fresh shared runs after each selected question, preserving
  the fix that prevents a later bulk purge restoring earlier deleted answers.
- `tests/test_question_delete_scaling.py`: bounded SQLite VM work for 500/1500 extra
  synthetic captures, shared/exclusive cases, preserved normalized answers, correct
  run removal and FK checks. Assert deletion previews never select raw result JSON.
- `tests/test_question_counts.py`: verify the additional index after reopening.
- `README.md`, `CHANGELOG.md`: behavior, startup and safe-update instructions.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_question_counts.py tests/test_question_data_deletion.py tests/test_removed_question_bulk.py tests/test_question_delete_progress.py`: **26 passed in 26.93s**.
- `.\.venv\Scripts\python.exe -m pytest -q -s tests/test_question_delete_scaling.py`: **5 passed in 4.69s**.

| Extra synthetic captures | Shared answers | SQLite VM steps | Selection + purge seconds |
| --- | --- | --- | --- |
| 500 | No | 89,900 | 0.027 |
| 1,500 | No | 268,900 | 0.066 |
| 500 | Yes | 135,900 | 0.055 |
| 1,500 | Yes | 406,900 | 0.255 |

These are offline synthetic metadata measurements with only the small fixture's
saved images, not a live deletion benchmark or a completion-time prediction. The
SQL-work guard is the regression criterion; timings vary by machine/load.

- `.\.venv\Scripts\python.exe -m pytest -q`: **397 passed, 4 skipped in 156.66s**.
  Skips are the opt-in hardware tests.
- `git diff --check`: passed.

## Activation and limits

The previous progress dialog is merged, but the old process remained busy and
rejected managed restart with `storage_unavailable`. New requests handled by that
old process cannot show newly implemented UI. The dialog cannot attach to an
already-submitted deletion request. After a safe restart and page refresh, it will
appear for subsequent single/bulk confirmations; it is deliberately indeterminate.

Do not stop the active deletion or build indexes in its live database. All writes
and purge tests here used disposable synthetic databases. No live records were
deleted for testing, no imagery was inspected, and no camera/model/GPU test ran.
The existing hardware/model revision remains unchanged (historical Liquid revision
`051bcc464b01b9f92942b364d9586b0ef5912432`).

Image bytes still need secure clearing and checkpointing. This patch removes
avoidable table scans; it does not promise constant-time deletion or bypass the
single atomic transaction. The next Phase 4 check is safe activation once work has
settled, followed by a user-intended deletion and progress-dialog verification.
Phase 5 remains unauthorised; do not auto-merge or test by deleting user records.
