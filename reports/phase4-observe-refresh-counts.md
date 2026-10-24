# Phase 4 — Observe refresh and live counts

Date: 24 October 2026

## Changes

- `src/vop/dashboard.py`: replace the all-camera refresh barrier with independent,
  non-overlapping camera requests on the existing 0.2-second timer. Add five-second
  timeouts to metadata/lease and answer requests. Keep decoded image replacement,
  image visibility, masking, leases and background-tab suspension.
- Active/Unknown numbers previously remained at page-load values while answer
  tables changed. Reuse the authenticated, ETag-aware per-camera answer route to
  return current counts. Closed panels request counts only once per second; open
  answers poll every 0.2 seconds. Unchanged responses skip history replay. Sum only
  the cameras represented on the current page. Hidden answer content is not redrawn.
- Count ACTIVE and RECOVERING as active, since an episode ends only after the
  configured negative confirmations. PENDING and OBSERVED do not count as confirmed
  active conditions. Stale or disabled questions remain Unknown. Initial rendering
  and live responses use the same counting function.
- `tests/test_observe_image_refresh.py`: stall one camera and prove that another
  keeps refreshing without overlapping stalled requests. Existing decode/visibility
  checks remain.
- `tests/test_observe_answer_refresh.py`: exercise hidden-panel count updates,
  multi-camera totals, open-panel updates, errors, ETags and tab visibility.
- `tests/test_camera_answer_groups.py`: compare count headers with answer states,
  count-only responses, no replay for unchanged ETags, stale Unknown transitions,
  and Pending → Active → Recovering → Inactive in explicit synthetic fixtures.
- `README.md`, `CHANGELOG.md`: document behavior and target-rate limits.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_image_refresh.py tests/test_observe_answer_refresh.py tests/test_camera_answer_groups.py tests/test_observe_camera_selection.py`: **9 passed in 7.70s** before adding the lifecycle case.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_camera_answer_groups.py::test_live_count_matches_active_and_recovering_episode_on_page`: **1 passed in 4.03s**.
- `.\.venv\Scripts\python.exe -m pytest -q`: **386 passed, 4 skipped in 161.71s**.
  Collection preceded the added lifecycle test, which passed separately as recorded above.
  The four skips are the opt-in hardware tests.
- `git diff --check`: passed.
- Authenticated JSON managed restart: HTTP 202; new instance ready; all three source
  control tuples (enabled, retention, interval) unchanged. Observation count
  33273 → 33277 during restart verification. Existing user monitoring resumed.
  No camera/model test or live settings submission was requested by this validation.

## Limits and next check

No visual browser test, camera frame-rate measurement, new model benchmark or GPU
validation was performed. Synthetic tests establish refresh isolation and counting,
not a measured 5 fps on the user's network. The decoder still targets 5 fps; actual
throughput depends on the camera, network and decoding. Slow image downloads can
still delay that individual camera. Counter updates follow completed observations,
not objects visible in the live preview; confirmation and stale-gap policies remain.
No model revision or hardware configuration changed (historical approved Liquid
revision: `051bcc464b01b9f92942b364d9586b0ef5912432`). Stay within Phase 4: refresh
Observe once to load the scripts, then compare visible episode states with the live
counter and image cadence. Phase 5 remains unauthorised. Do not auto-merge.
