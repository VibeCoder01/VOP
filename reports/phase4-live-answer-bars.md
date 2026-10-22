# Phase 4: live answer panels and value bars

22 October 2026. Owner request: update shown answers as fast as possible and show
value bars per question. This extends the Phase 4 foreground viewing workflow.

## Changed files and behavior

- `src/vop/dashboard.py`: open panels check immediately, then every 0.2 seconds.
  Each panel polls independently without overlapping requests. Hidden tabs and closed
  panels make no answer requests. Conditional ETags return 304 when unchanged; replace
  only changed table content, preserving disclosures, image elements and the page.
  The read-only server HTML route uses existing summaries and immutable question scales.
  Cheap revision checks avoid full-history replay on unchanged polls and detect fresh
  samples, question/control changes, expiry, deletion, raw-score retention and app restart.
- Add accessible native meter bars and numeric labels: Liquid Yes scores where their
  semantics are known; otherwise Yes=1/No=0 without invented confidence. Ordinal values
  use the configured 0-to-last-level range and retain level names/numeric values. Choice
  options use native option scores when available, otherwise selected/unselected bars.
  Tooltips describe scale meaning. Native model percentages are not calibrated accuracy
  or probabilities. Unknown/stale/failed/disabled values have no numeric bar.
- `src/vop/browser_auth.py`: allow authenticated View-mode answer fragment/script reads;
  preserve role/origin controls. No image pixels or raw payloads are sent by this route.
- `tests/test_camera_answer_groups.py`: camera isolation, all value types/native scores,
  fractional ordinal positions, new samples, conditional no-replay responses, raw-score
  retention, same-sequence gap deletion, expiry, failure versus No, auth and read-only use.
- `tests/test_observe_answer_refresh.py`: Node DOM harness verifies open-only polling,
  hidden pause, pending-request exclusion, 304 handling, no closed-panel mutation and
  failure/retry while retaining the last table.
- README and CHANGELOG document behavior, scales and remaining limits.

## Commands and actual results

- `.\.venv\Scripts\python.exe -m compileall -q src/vop`: passed.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_camera_answer_groups.py tests/test_observe_answer_refresh.py tests/test_observe_images.py tests/test_observe_image_refresh.py`:
  9 passed in 4.40s before final retention/failure checks.
- `.\.venv\Scripts\python.exe -m pytest -q`: 350 passed, 4 skipped in 109.97s,
  before the final latest-native-payload revision refinement and added No/failure test.
- Final `.\.venv\Scripts\python.exe -m pytest -q tests/test_camera_answer_groups.py tests/test_observe_answer_refresh.py`:
  5 passed in 7.26s, including raw-score retention and No/failure behavior.
- `git diff --check`: passed.
- Applied through authenticated managed restart: HTTP 202, new instance ready,
  camera enabled/evidence/interval controls preserved; observations 8524 -> 8526 while
  existing monitoring drained/resumed. No keys, camera details or private images logged.

CI results are tracked in the pull request.

## Limits and next acceptance

All automated inference/frame fixtures were explicitly synthetic. No new live camera
validation, actual browser visual check, model download or GPU benchmark was performed.
No model/runtime changes; historical approved revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

The 0.2-second check is a target plus request/render time, not measured end-to-end
latency. Answers can only change after an observation finishes; live images update
independently. Polling does not increase inference cadence, capture images, store data,
change monitoring or share provider confidence scales. Without JavaScript, native
Show/Hide still works and Refresh view updates the answers.

Refresh Observe once, open one or more panels and confirm fresh answers/bars update
while panels stay open and images continue. Continue Phase 4 manual acceptance;
Phase 5 remains unauthorised. Do not auto-merge.
