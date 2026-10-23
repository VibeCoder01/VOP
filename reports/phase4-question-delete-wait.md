# Phase 4 — question deletion waits for active work

Date: 23 October 2026

## Change

Single and bulk permanent question deletion previously returned an overload error
when request admission, observation or alert processing was busy. Both routes now
wait for admission, then acquire observation and alert locks in the existing order.
Blocking waits run in worker threads; the dashboard event loop stays responsive.
The confirmation page and README explain that the page must stay open while waiting.

The entire removed-question selection and its recorded-data fingerprint are checked
after all locks are acquired, before any writes. Changed data returns updated counts
for a new confirmation. The transaction, rollback, fresh shared-run reads and
unselected-answer protection are unchanged. Authentication, Configure mode, CSRF
and origin checks still run before waiting. Other operations keep their existing
admission behavior, including manual capture scheduling and queued camera saves.

## Changed files

- `src/vop/browser_auth.py`: waitable admission for question deletion.
- `src/vop/removal.py`: wait for observation/alerts and explain the wait.
- `tests/test_removed_question_bulk.py`: deterministic real-lock tests for single and
  bulk deletion, responsive health reads and changed-data rechecks during a wait.
- `tests/test_question_data_deletion.py`, `tests/test_removal.py`: replace obsolete
  permanent-deletion busy-rejection expectations; retain access and rollback checks.
- `README.md`, `CHANGELOG.md`, this report: behavior and validation evidence.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q`: **365 passed, 4 skipped** in 100.34s.
- `git diff --check`: passed.
- Authenticated managed `POST /ui/restart`: HTTP 202; new instance ready, source
  enabled/evidence/interval controls preserved. Observations 16426 -> 16430 while
  existing monitoring drained/resumed. No deletion was submitted to the user app.
- Initial targeted run exposed two test expectations that included the deliberately
  changed image-saved flag; corrected the expected post-change snapshot. The final
  full suite above includes all contention, stale-preview and rollback cases.

CI results are tracked in this change's PR.

## Limits and next acceptance

Destructive tests use disposable synthetic histories only. No user questions or data
were deleted. No new camera connection, model download, GPU benchmark or real browser
visual test was initiated. No model/runtime changes; historical approved revision
remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

The deletion request waits in memory, not a persistent background job. Keep the page
open until completion. Monitoring can stay on. Changed data requires confirmation
again. Existing backups, exports and previously sent messages are unchanged.

Refresh Questions and retry the intended selection. Continue Phase 4 acceptance;
Phase 5 remains unauthorised. Do not auto-merge.
