# Phase 5: Monitoring storage recovery

## Findings

The user's screenshot came from the monitor POST returning the catch-all SQLite error handler. A read-only check found the affected source already paused (sample interval 0), so its controls were committed before the failure. Metadata reads worked (0.08s for controls/counts); C: had about 15 GB free. The current database was about 11.4 GB with 62,619 observations across four sources. No integrity scan, image read, model/camera request or real database write was performed. The original SQLite exception/code was not retained by the previous handler, so its exact cause cannot be established. Contention is a plausible explanation, not a confirmed finding.

The handler performed source-control writes and full temporal pause-gap saving/replay synchronously on the HTTP event loop. SQLite connections wait five seconds for another writer, after which the generic JSON response offered no remediation and no exception-code logging.

## Changes

- src/vop/monitoring.py: thread-worker monitoring routine, with at most three attempts per busy/locked step and 0.1s between attempts. Other errors propagate immediately. Retry only the failed step, not already committed source settings. Preserve saved interval and evidence/enabled controls. Validate questions before starting changes.
- src/vop/dashboard.py: offload complete monitoring storage/gap work through run_in_threadpool. Worker-session shutdown remains off loop.
- src/vop/service.py: readable browser storage error explains partial completion and checking current state. API keeps storage_unavailable and adds remediation. Terminal logs SQLite class/error name only, no SQL/parameters/credentials/images.
- tests/test_monitor_storage_recovery.py (new), README.md, CHANGELOG.md, pyproject.toml (0.6.21), this report.

## Validation

`.venv/Scripts/python.exe -m pytest -q tests/test_monitor_storage_recovery.py tests/test_operator_workflow.py tests/test_observe_grid.py` — **35 passed in 86.71s**. New tests cover busy retry/exhaustion, no retry for I/O errors, interval restoration, only failed-step retry, partial-pause HTML/API errors and a delayed monitoring write while a health request succeeds on the same event loop. SMTP, cameras, model/GPU, sounds, Tapo and SMS not exercised.

`.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .` installed 0.6.21; `git diff --check` passed. Existing model revision/measurements unchanged. No service restart or real settings edits. CI and live UI unverified.

## Limits / next

These changes remove event-loop blocking and recover bounded transient contention, but do not prove the original error's cause or eliminate long database writers/full-history temporal replay. Retries can still exhaust, and a pause may already be committed when recording its gap fails. The new message makes this explicit; retained SQLite codes make future occurrences diagnosable. Check Observe after restart before starting/pausing again. Finish Phase 5 review/CI; no Phase 6 authorisation assumed.
