# Phase 4: per-camera answers on Observe

22 October 2026. User-requested UI change within Phase 4.

## Changes

- `src/vop/dashboard.py`: replace the shared Latest answers table with a table
  inside each camera’s Observe section. Its Show answers / Hide answers control
  is a native, keyboard-accessible details/summary disclosure styled as a button.
  Each starts hidden and opens independently, with no JavaScript or server mutation.
  Keep question versions, states, answer formatting and local observation timestamps;
  remove the redundant Source column from camera-specific tables.
- `tests/test_camera_answer_groups.py`: two cameras with the same question ID and
  different question text/values remain separate; verify collapsed groups and both
  labels, viewer read access, source filtering and no observation-count changes.
- README and CHANGELOG describe the behavior.

## Verification and application

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_camera_answer_groups.py tests/test_ordinal_labels.py tests/test_metric_help_camera_names.py tests/test_observe_images.py tests/test_ui_modes.py`:
  21 passed in 7.22s, using offline synthetic fixtures only.
- `git diff --check`: passed.
- Applied through authenticated managed restart: HTTP 202 and new instance;
  camera enabled/evidence/interval settings preserved, observations 6664 -> 6664.
- No live-camera test, model download, GPU benchmark or new model measurements.
  Approved historical model revision remains
  051bcc464b01b9f92942b364d9586b0ef5912432.

## Limits and recommendation

The answer tables start collapsed again on reload. Answer refresh behavior is
unchanged: Refresh view updates the recorded results; opening/closing a table does
not capture or start monitoring. Existing image refresh and green/amber rings are
unchanged. No new browser dependency or persistence setting was introduced.

Continue Phase 4 user acceptance of the camera-specific answer layout. Phase 5
remains unauthorised; do not auto-merge.
