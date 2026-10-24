# Phase 4 — unified camera settings

Date: 24 October 2026

## Change and files

- `src/vop/integration_ui.py`: one editor, four groups (Camera, Connection,
  Observations, Recorded images), one Save. Network cameras edit model/address/account;
  USB cameras keep their existing device and use the same name/interval/image controls.
  Camera detail has one Edit settings action and a read-only settings summary. Remove
  duplicate visible Rename/observation-editor entry points; keep connection tests on
  the detail page. Old rename links redirect to the unified editor.
- Parse/validate the unified observation fields before protected connection writes,
  then save under the existing queued acquisition guard. Preserve controls when a
  legacy connection-only request omits the new form marker. Blank password keeps the
  protected password, including when the username changes. Pausing/disabling records
  the existing intentional gap marker. Names and controls remain persistent.
- `src/vop/dashboard.py`: route camera image-saving and old camera observation links
  to the unified editor, preserving the other-input editor. Add compact section/field
  spacing using the existing editor styles.
- `tests/test_unified_camera_settings.py`: grouped form, all field presence, old URL
  redirects, network/USB save and restart persistence, saved-password reuse, legacy
  control preservation, invalid-interval no-write checks and pause behavior.
- `tests/test_metric_help_camera_names.py`, `tests/test_observation_images_ui.py`,
  `tests/test_operator_workflow.py`, `tests/test_observe_camera_selection.py`: update
  canonical editor links, USB persistence and visible action-label expectations.
- `README.md`, `CHANGELOG.md`, this report: workflow and validation.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_unified_camera_settings.py tests/test_camera_save_queue.py tests/test_metric_help_camera_names.py tests/test_observation_images_ui.py tests/test_separate_setup.py tests/test_observe_camera_selection.py`:
  **23 passed in 17.39s** before the additional existing USB test was extended to
  exercise unified-save persistence.
- Initial targeted failures were old USB redirect and detail image-setting text/link
  expectations. Updated them to the requested single editor/action.
- `.\.venv\Scripts\python.exe -m pytest -q`: **383 passed, 4 skipped** in 141.59s.
- `git diff --check`: passed.
- Authenticated managed restart: HTTP 202; new instance ready, saved enabled/image-
  saving/interval controls preserved. Observations 29796 -> 29800 while existing
  authorised monitoring drained/resumed. No live settings form was submitted.
- CI is tracked in this change's PR.

## Limits and next acceptance

Synthetic/offline tests only. No user settings were submitted through the editor,
no new camera connection/model download/GPU benchmark/user-data deletion/browser
visual test was initiated. Historical approved model revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Protected credentials and SQLite configuration remain separate stores; no new
cross-store transaction is introduced. Existing USB device selection is displayed
and preserved, not reconfigured. Legacy POST observation/rename endpoints remain
compatible; their old GET editors redirect to this form. Other input types retain
their existing editor. Saving a nonzero interval can start monitoring only when
Camera enabled is on; the form explains that behavior.

Refresh Cameras, open Edit settings and check the four groups for Phase 4 acceptance.
Phase 5 remains unauthorised. Do not auto-merge.
