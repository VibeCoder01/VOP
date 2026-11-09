# Phase 5: Current-state UI before history

## Change

Version 0.6.23 separates current Observe data from historical metrics. Camera selection now filters sources before summary/config reads. Full/Grid Observe and their polling use indexed latest-answer reads and compact committed state snapshots; they never call historical replay or historical episode counts. Unused history summaries were also removed from legacy configuration navigation. The episode-count statistic/explanation belongs on Episodes, not Observe.

Snapshots contain only current state/value/provenance/timestamps/review status, no historical arrays or image bytes. Existing observation/startup temporal processing prepares them; connection-scoped updates publish only after successful commit and are discarded on rollback. The volatile cache is bounded at 2,048 question versions and is not a database table or backup configuration. Latest-row identity, value, status and timestamps validate snapshots; enabled/version controls and time-based staleness are applied on every read. A missing/stale snapshot never triggers history work: current recorded answers remain readable, with Unknown episode state until normal processing refreshes it. This does not change automation/temporal algorithms.

Full/Grid page rendering and saved-image HEAD polling now select frame metadata and BLOB length rather than fetching the PNG. Actual authorised GETs still return image bytes. Current response ETags include compact states, so changes remain visible; existing answer/frame race checks stay in place.

## Files

src/vop/storage.py; src/vop/dashboard.py; tests/test_fast_observe.py (new); tests/test_camera_answer_groups.py (strip rendered state whitespace in count assertion); tests/test_observe_image_pairs.py (inject race at the new current_summary entry point); README.md; CHANGELOG.md; pyproject.toml; this report.

## Validation and measurements

New regression tests forbid Store.summary, _history, _rebuild and event_count during camera selection/answer polling, reject access to excluded cameras, and forbid image payload reads during Full/Grid/HEAD requests. They also compare current answers/episode states against replay, test staleness/disable controls, prove rollback cannot publish a snapshot, isolate caller mutations, and prevent retention gaps from resurrecting cached values.

`.venv/Scripts/python.exe -m pytest -q tests/test_fast_observe.py` — **3 passed in 4.95s**.

`.venv/Scripts/python.exe -m pytest -q tests/test_metric_help_camera_names.py tests/test_fast_observe.py` — **7 passed in 8.58s**, after moving the historical episode-count tooltip to Episodes.

Synthetic benchmark: disposable test-phase3 store, one question with 5,001 eligible answers, existing _rebuild run once to seed committed state. Seven alternating direct calls to summary/current_summary, medians **494.48 ms / 5.41 ms**, about **91×** faster for this summary operation. Latest answer, state, observation ID and staleness matched. The full offline suite was running concurrently, so this is illustrative local synthetic evidence, not a controlled whole-page production benchmark or hardware/model inference timing.

No live camera, image inspection, model weights/GPU, device/email/audio/SMS operation or real database write/replay was used. Model revision and historical measurements unchanged. Editable installation uses `.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .`. Service not restarted. CI and live page performance remain unverified.

## Limits / next

Historical aggregations on requested Trends/Episodes pages, existing startup replay and observation-side temporal rebuilds remain. Navigation no longer requests those calculations; this change does not claim to eliminate background CPU/write contention. A cold or externally changed snapshot can temporarily show Unknown episode state while still displaying the latest valid answer. No history is dropped. Finish Phase 5 review/CI and load through Start VOP; Phase 6 remains unauthorised.


Final validation: `.venv/Scripts/python.exe -m pytest -q tests/test_fast_observe.py tests/test_metric_help_camera_names.py tests/test_camera_answer_groups.py tests/test_observe_grid.py tests/test_observe_image_pairs.py tests/test_phase3_release.py` — **50 passed in 48.51s**.

Full run `.venv/Scripts/python.exe -m pytest -q` — **567 passed, 6 skipped, 1 failed in 304.64s**. The sole failure was the existing episode-count help assertion after removing that historical counter from Observe. Its explanation was moved to the historical Episodes page; that check and the final 50-test selection passed in a fresh process. The entire suite was not repeated after this final display fix. No claim of final full-suite or CI success. `git diff --check` passed.
