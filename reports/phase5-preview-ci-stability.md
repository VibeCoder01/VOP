# Post-merge preview-test timeout — 30 October 2026

PR #68's pull-request checks passed on Windows and Ubuntu. The separate push run
for merge commit `3025af4fd595a13d0b652fa8107f34fe440122df` failed on Windows:
run https://github.com/VibeCoder01/VOP/actions/runs/41097716107, original job
124207690408. Ubuntu passed. The earlier status response checked only the PR run
and omitted this later result.

The failing test was
`test_processed_pair_keeps_completed_frame_until_new_answers_commit`, at
`pending.result(timeout=5)` after releasing synthetic inference. Its in-flight
frame identity, pixel privacy, completed-image association and live-preview checks
had passed. Original Windows totals: 1 failed, 510 passed, 6 skipped. The log does
not identify precisely where the remaining work was blocked; no product assertion
or navigation-order failure was reported.

The shared `no_workers` fixture disabled sampling and alert workers but had not been
updated for the newer Actions background worker. It now disables all three, leaving
the explicitly controlled inference thread running. The image-pair functional test
uses bounded waits of 10 seconds for entry and 30 seconds for release/completion
instead of assuming a complete post-release database write finishes within five
seconds on every Windows CI runner. No assertion, deadline implementation or app
timeout was removed or changed. A continuing stall still fails after the bound.

## Validation and files

- Changed `tests/test_removed_question_bulk.py`, `tests/test_observe_image_pairs.py`
  and README CI/testing guidance. This report records the failure and correction.
- `.venv\Scripts\python.exe -m pytest -q tests/test_observe_image_pairs.py tests/test_removed_question_bulk.py tests/test_mask_editor_browser.py`:
  **22 passed in 45.76 seconds**.
- `.venv\Scripts\python.exe -m pytest -q tests/test_history_camera_buttons.py tests/test_observe_camera_selection.py tests/test_question_counts.py tests/test_question_delete_progress.py tests/test_question_delete_scaling.py tests/test_trends_camera_buttons.py tests/test_unified_camera_settings.py tests/test_episodes_timeline.py`:
  **29 passed in 49.00 seconds**, covering other users of the shared fixture.
- `git diff --check`: passed. No runtime source, package version, dependency or
  schema changed. No live app restart is needed for these test-only changes.
- Requested a rerun of the failed jobs on the original main run. Its final outcome
  and the fix PR's Windows/Ubuntu checks are recorded on that PR; no success is
  assumed here.

No real camera, GPU/model, device, microphone, audio, email/SMS or live visual tests
were run. All image pixels were synthetic. Model revision and hardware measurements
are unchanged. Check the actual merged main commit's push run in future status
reports, alongside PR checks. Remain in Phase 5; Phase 6 is not started and no PR
is auto-merged.
