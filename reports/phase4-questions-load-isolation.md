# Phase 4 — isolate Questions configuration from recorded history

Date: 24 October 2026

## Architectural diagnosis

Questions was a configuration page synchronously waiting for history analysis for
all rows. The previous count-only fix removed payload hashing/per-capture calls but
left history in the initial request. SQLite's actual plan materialised the other-
answers table and then SCANned it once for every selected run. A fixed number of SQL
statements did not guarantee bounded SQL work. Frame lookups also used the table's
primary key rather than an evidence-presence metadata index.

Read-only measurement of 11 current question count workloads: **45.898 s** total,
including individual questions at 6.690 s and 16.171 s. After removing the temporary-
table join but before adding covering metadata indexes, the same count workload was
still 54.224 s. These are count-function measurements, not browser navigation tests;
monitoring continued, so the database was not frozen. No identifiers, result values,
credentials or image pixels were printed. This supersedes the earlier report's
smaller removed-definition benchmark as evidence for the current Questions page.

## Change and files

- `src/vop/removal.py`: initial question rows show configuration/actions and count
  placeholders. A separate authenticated HTML count fragment runs in a worker thread.
  One small self-hosted script fills count cells only, preserving checkboxes, edit
  focus and rows; it handles timeout/failure with Retry counts. No automatic polling,
  persistent count cache, new JSON UI API or frontend dependency is added.
- `src/vop/dashboard.py`: load the script on Questions only and stop constructing
  the duplicate unused question-data list. Initial configuration no longer depends
  on history counts or deletion preview data.
- `src/vop/history_deletion.py`: group observations once per run and join directly
  to indexed run/evidence metadata, eliminating the repeated temporary-table join.
  Detailed deletion fingerprints and all data-validation/deletion semantics remain.
- `src/vop/storage.py`: idempotent `observations_count_lookup` covering index and
  partial `frames_with_evidence` index, created for new and existing databases on
  startup. Indexes contain metadata only; no table/schema-version migration is needed.
- `tests/test_question_counts.py`: forbid history counts in initial configuration;
  verify bounded SQLite VM work at larger history sizes, index creation/reopen,
  responsive configuration/health during stalled counts, fragment access/filtering,
  and JavaScript cell updates, failure/timeout/retry and preserved selection.
- `tests/test_phase2_browser_storage.py`: allow the specific self-hosted Questions
  script while retaining the no-external-assets/inline-script checks.
- `tests/test_removed_question_bulk.py`: counts are checked in the fragment while
  initial controls and camera filtering remain available.
- `README.md`, `CHANGELOG.md`, this report: behavior and validation evidence.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_question_counts.py`:
  **6 passed in 5.62s**.
- The first targeted run caught a test following a Configure-mode redirect; fixed
  the test to inspect the redirect itself. No access control was weakened.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_phase2_browser_storage.py::test_all_views_native_markup_and_no_external_assets tests/test_question_counts.py`:
  **7 passed in 5.04s**.
- The first full suite had 375 passed, 4 skipped and one stale asset-allowlist
  expectation. Updated it to permit only the self-hosted Questions script, retaining
  the checks against external/inline script content.
- Final `.\.venv\Scripts\python.exe -m pytest -q`: **376 passed, 4 skipped** in
  132.15s. `git diff --check`: passed.
- Managed `POST /ui/restart`: HTTP 202; new instance ready, source monitoring/evidence/
  interval controls preserved. Observation count 24355 -> 24355. Index construction
  completed on normal startup; no user records were deleted.
- After index creation, the read-only count workload for the 11 current questions
  took **0.416 s**, versus the earlier 45.898 s. This still measures count functions,
  not browser navigation. Initial page rendering no longer calls those functions.
- CI is tracked with this change's PR.

## Limits and next acceptance

Tests use disposable synthetic data. Real database diagnostics use metadata only;
no user data was deleted, no camera connection/model download/GPU benchmark or real
browser visual test was initiated. No inference/model/runtime changes; historical
approved model revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Configuration does not wait for history counts. Counts require JavaScript on this
listing; without it, deletion confirmation still shows its current counts. Counts
are a snapshot and can change during monitoring. Retry is explicit after failure.
Browser timeout does not kill a database operation already running in its thread.
The indexes require a one-time startup build and normal maintenance on writes.
Counts still scale with history and displayed question count; per-source batch
aggregation is a possible next optimisation only if measured workloads require it.

Refresh Questions for Phase 4 acceptance. Phase 5 remains unauthorised. Do not auto-merge.
