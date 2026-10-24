# Phase 4 — one camera entry and page

Date: 24 October 2026

## Change and files

The previous change unified the editors but retained a separate camera overview and
two visible entry actions. This change removes that remaining split.

- `src/vop/integration_ui.py`: active camera rows have one Manage camera button.
  `/cameras/{id}` now renders the editable camera form directly, titled with the
  camera name and monitoring state. It contains Camera, Connection (prerequisites,
  last-test state), Observations and Recorded images.
  Questions and Remove camera follow the settings. The first/default submit button is Save settings, so Enter does not run a connection
  test. One normal Save action persists settings; Save and test is an explicit alternative using all current form values.
  Old /edit and /rename GET routes redirect to the canonical page. Notices remain
  visible after save. Cancel returns to Cameras.
- `src/vop/dashboard.py`: existing image-saving/observation links target canonical
  camera anchors; add restrained spacing for the related Questions/Remove sections.
- `src/vop/ui_readiness.py`: camera remediation links use the same canonical page.
- `tests/test_unified_camera_settings.py`: protect the single camera-row action,
  complete page, canonical redirects, no nested forms and save-before-test behavior
  with synthetic capture and no inference.
- `tests/test_metric_help_camera_names.py`, `tests/test_observation_images_ui.py`,
  `tests/test_observe_camera_selection.py`, `tests/test_operator_workflow.py`,
  `tests/test_history_deletion.py`: update
  canonical URL/action expectations. The legacy rename POST test inspects mutation
  without following its redirect while secrets are forbidden; opening the editable
  page afterwards appropriately reads protected prefill values.
- `README.md`, `CHANGELOG.md`, this report: workflow and evidence.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_unified_camera_settings.py tests/test_observe_camera_selection.py tests/test_separate_setup.py tests/test_metric_help_camera_names.py tests/test_observation_images_ui.py tests/test_operator_workflow.py`:
  **38 passed in 27.20s**.
- The initial targeted run caught outdated URL/action expectations and the rename
  test's redirected prefill read; updated them to distinguish mutation from rendering.
- `.\.venv\Scripts\python.exe -m pytest -q`: 384 passed, 4 skipped and one old
  assertion expecting Remove on the camera list (155.76s). Updated that assertion
  to require Remove on the camera page and its absence from the camera list.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_history_deletion.py::test_camera_remove_is_visible_and_restore_returns_to_cameras`:
  **1 passed in 2.21s**.
- After putting Save first in the form's submit order:
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_unified_camera_settings.py`:
  **5 passed in 5.30s**. The default-submit check prevents Enter from running a test.
- `git diff --check`: passed.
- Authenticated managed restart: HTTP 202; new instance ready, enabled/image-saving/
  interval settings preserved. Observations 31169 -> 31173 while existing authorised
  monitoring drained/resumed. No live settings/test form was submitted.
- The final full suite is also run by both platform jobs in CI.
- CI is tracked in this change's PR.

## Limits and next acceptance

Offline/synthetic tests only. No user settings form was submitted, no new camera
connection/model/GPU benchmark/user-data deletion or browser visual test was initiated.
Historical approved model revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Connection testing deliberately opens its result/preview page, with Back to camera
returning to this same editable page. USB device selection remains displayed and
preserved; network connection testing remains limited to the supported RTSP cameras.
Existing protected-settings and persistence limits are unchanged. There is no new
model/backend coupling or dependency.

Refresh Cameras and use Manage camera for Phase 4 acceptance. Phase 5 remains
unauthorised. Do not auto-merge.
