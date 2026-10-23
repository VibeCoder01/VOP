# Phase 4: compact Observe controls and steady Trends

23 October 2026. Owner requested grouped mode controls, no vertical Trends refresh
movement, aligned monitoring/answer buttons, clearer labels and less answer padding.

## Changed files

- `src/vop/dashboard.py`: group the existing current-mode indicator and single mode
  toggle inside a named sidebar control. Preserve current mode, permissions and forms.
  Put monitoring actions and native answer disclosure in one flow-root control group;
  summaries sit beside the action row where width permits, with answer content cleared
  underneath at full width. Narrow layouts can wrap. Keep native keyboard behavior,
  independent Show/Hide panels, image visibility and existing read-only polling.
- Scope tighter cell/version/bar padding to the live camera answer tables. Change only
  their State column to Episode State. Shared ordinal labels omit the Expected level
  prefix while preserving configured level names, fractional positions and one-decimal
  numbers, including immutable historical versions. Stored values remain unchanged.
- Trends: the shared entrance animation translated the workspace vertically by four
  pixels whenever a whole page loaded. A Trends-only class disables that animation.
  Keep its existing ten-second refresh and filter/hidden-tab safeguards.
- `tests/test_camera_answer_groups.py`, `tests/test_ui_modes.py`: control grouping,
  live Episode State header and existing camera/mode isolation checks.
- `tests/test_ordinal_labels.py`: prefix-free boundary/fractional/historical labels,
  escaping and unchanged stored numeric values.
- `tests/test_trends_refresh.py`: Trends-only no-animation class and existing refresh
  safeguards/auth/no-acquisition behavior.
- README and CHANGELOG describe the controls, labels and refresh behavior.

## Commands and results

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_ordinal_labels.py tests/test_camera_answer_groups.py tests/test_ui_modes.py tests/test_trends_refresh.py`:
  19 passed in 8.33s.
- `git diff --check`: passed.

- `.\.venv\Scripts\python.exe -m pytest -q`: 356 passed, 4 skipped in 81.87s.
- Authenticated managed restart: HTTP 202 and a new instance ready; camera enabled,
  image-saving and interval settings preserved. Observations 12238 -> 12242 while
  existing monitoring drained/resumed. No private images or credentials inspected.

CI results are tracked with this change's PR.

## Limits and next acceptance

Verification uses synthetic TestClient HTML, CSS assertions and the existing Node
refresh-script harness. No actual browser visual inspection, live camera test,
model download or GPU benchmark was performed. No model/runtime changes; the
historical approved revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Trends still refreshes the page; this removes its explicit four-pixel entrance
animation. Changes in actual result content can still affect layout. Manual visual
acceptance should check refresh stability and button wrapping on desktop/mobile.

Refresh Observe/Trends once to load new CSS. Continue Phase 4 manual acceptance;
Phase 5 remains unauthorised. Do not auto-merge.
