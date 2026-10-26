# Phase 4 — runtime loop efficiency review

Date: 26 October 2026

## Scope and outcome

Reviewed Python loop/comprehension sites throughout `src/vop`, the embedded browser
polling loops, and relevant launcher/build/smoke/benchmark loops in `tools` and the
Windows launcher. This is a static/data-flow review with offline regression checks,
not a claim that all loops are constant-time or a real-camera/GPU profile. AST counts
include comprehensions, not loop text inside comments or embedded JavaScript.

Inventory: 37 runtime Python files, 28 containing loops, 388 loop/comprehension sites after the fixes.

| Runtime module | Sites | Review / disposition |
| --- | ---: | --- |
| `benchmark.py` | 14 | Finite case/repetition loops and watchdog sleep/deadline; opt-in only. |
| `browser_auth.py` | 2 | Rate-window expiry and bounded request streaming; authentication guards retained. |
| `config.py` | 13 | 32-source/question and finite configuration validation. |
| `contracts.py` | 6 | Finite schema/question validation and result coverage. |
| `dashboard.py` | 66 | Batched answer reads; retained independent/non-overlapping visible-page polls and bounded render loops. |
| `environment.py` | 3 | Small finite environment inventory; not a hot path. |
| `history_deletion.py` | 21 | Replaced per-capture image-count queries with one aggregate; retained atomic per-record purges. |
| `inference/liquid_d1.py` | 9 | Bounded question/option conversion and validation; no new model execution. |
| `inference/mock.py` | 1 | Explicit synthetic question loop retained. |
| `inference/remote.py` | 4 | Bounded HTTP/request validation and provenance conversion. |
| `inputs/sources.py` | 1 | Finite private-destination policy normalization; acquisition uses guarded adapters. |
| `integration_ui.py` | 22 | Bounded setup lists and uniqueness retries; protected writes unchanged. |
| `live_preview.py` | 12 | Producer capped at 5 fps, four leases; pipe blocking/draining and Event waits avoid spin. Cleanup lock noted below. |
| `live_workspace.py` | 13 | Explicit live-workspace startup cleanup scans; single transaction retained. |
| `measurements.py` | 15 | Required linear ordered replay; interval/window passes are linear, not nested history searches. |
| `operator_workflow.py` | 2 | Bounded recovery deadline, sleeps and single recovery lock. |
| `pipeline.py` | 24 | Bounded questions/ROI groups and provider validation; capture remains serialized. |
| `preprocessing.py` | 1 | Bounded mask list; privacy processing retained. |
| `release_ui.py` | 26 | UI/configuration lists and exports; validation and native controls retained. |
| `reliable.py` | 51 | Fixed cycle reuse, batching, repeat retention writes, membership sets and streaming hashes. |
| `removal.py` | 23 | Bounded selected-question batch; current snapshots and rollback preserved. |
| `sampling.py` | 3 | 32-input bound, round-robin, one capture per tick; Event wait, no frame backlog. |
| `secrets.py` | 5 | Finite account/package lookup and bounded credential validation. |
| `service.py` | 8 | Bounded request streaming and source/question API loops; distinct metric replays retained. |
| `storage.py` | 21 | Added query-aligned indexes; full temporal replay per answer remains a scaling ceiling. |
| `ui_readiness.py` | 3 | Finite dependency checks; no camera/model acquisition from rendering. |
| `worker.py` | 7 | Blocking pipe receive, request deadlines, maximum 16 cached results; no spin polling. |
| `worker_protocol.py` | 12 | Bounded question/answer validation; safety checks retained. |

## Changed files and regression evidence

- `src/vop/reliable.py`: cache question maps, summaries, controls and observation
  provenance only within an evaluation. Eight rules for one question now need one
  replay/control/question read and one shared provenance lookup on first transition;
  the unchanged next evaluation reads no provenance. State, new versions, disabled
  controls, UNKNOWN suspension and alert identity semantics are retained. Delivery
  listing uses batches of at most 900 IDs: 12 alerts use two SELECTs, 905 use three,
  instead of one delivery query per alert. Retention selects uncleared raw runs only
  and updates images only while non-NULL. Configuration builds its version/question
  membership sets once. Backup and restore use Python 3.11 `hashlib.file_digest`
  through `file_sha256`, avoiding whole-database `read_bytes` allocations.
- `src/vop/storage.py`: idempotently install `observations_question` on source,
  question, version, sequence; and partial `frames_latest_evidence` on source and
  descending capture time. Query-plan checks require indexed seeks without temp
  sorts for history/newest saved-image reads, including after reopening.
- `src/vop/dashboard.py`: load the camera's native answer JSON in one parameterized
  query, rather than opening a connection/query per question. Graphs and states
  remain covered by the existing camera-answer tests.
- `src/vop/history_deletion.py`: one aggregate counts selected retained images,
  replacing a SELECT for every capture. Existing scope/FK/rollback checks remain.
- `tests/test_loop_efficiency.py`: nine offline regression cases cover cycle-local
  reuse and freshness, retention idempotent writes, delivery batch boundaries,
  indexes, answer batching, image count aggregation, and bounded streaming hashes.
  A guarded file verifies checksum reads stay within 256 KiB buffers; backup/restore
  tests forbid `Path.read_bytes` while retaining manifest validation.
- `README.md`, `CHANGELOG.md`, this report: behavior and review limitations.

## Commands and results

- `.\.venv\Scripts\python.exe -m compileall -q src/vop`: passed.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_loop_efficiency.py`: **9 passed in 5.75s**.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_loop_efficiency.py tests/test_history_deletion.py tests/test_phase3_release.py tests/test_camera_answer_groups.py`: **40 passed in 34.02s** before the two streaming-hash tests; all included again in the final suite.
- `.\.venv\Scripts\python.exe -m pytest -q`: **406 passed, 4 skipped in 161.33s**.
  Skips are the opt-in hardware tests.
- `git diff --check`: passed.
- Safe activation: two idle JSON health checks, managed restart HTTP **202**, new
  instance ready; all three source-control tuples unchanged. Observation count
  **16477 → 16477** during verification. Read-only SQLite metadata confirmed both
  `observations_question` and `frames_latest_evidence` were installed. No live
  deletion, backup/restore, camera connection or model test was submitted.

## Remaining architectural costs

1. `Store.save → _rebuild → replay` still replays a question's entire history and
   rewrites materialized events for each new answer. Per-answer work grows with its
   history; cumulative recording cost can be quadratic. The index removes unrelated
   source/question scans, not this replay cost. Incremental replay/checkpoints need a
   dedicated design and equivalence tests for confirmations, stale/UNKNOWN gaps,
   version changes, deletions, time windows, backups and late/out-of-order answers.
   This is the highest-priority next performance change within the existing scope.
2. Metric/export/API views deliberately replay each distinct question/version and
   may process complete history. Live answer ETag checks still count camera history
   to detect edits/deletions before deciding whether replay is needed. A durable
   revision/checkpoint scheme could remove this remaining scan; none was invented
   in this small review patch.
3. Preview worker shutdown can join while holding the preview lock (up to four
   workers, bounded teardown). Moving teardown outside the lock needs focused
   concurrency tests. Image clearing/checkpoint and SQLite backup still do real
   disk I/O; no runtime/time estimate is promised.
4. Small capped validation/ROI/criteria loops, process waits, monitoring scheduling,
   explicit maintenance scans and synthetic fixture loops remain. No safety checks,
   backoff, capture fairness, privacy masks or provider provenance were removed for
   a micro-optimization. Test loops were not targets for cosmetic rewriting.

## Hardware and next acceptance

No live data was deleted, no real camera connected, and no model/GPU run or new
benchmark was performed. Offline fixtures and temporary databases supplied all
regression evidence. Historical approved Liquid revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`. No inference hardware, score semantics or
model revision changed. After offline checks, activate only during a safe managed
restart and preserve source controls. Next Phase 4 acceptance is ordinary UI/alert
behavior with the performance fixes, followed by focused incremental-replay work;
Phase 5 is unauthorised. Do not auto-merge.
