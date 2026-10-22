# Phase 4: Observe image visibility

22 October 2026. Owner requested per-camera Show/Hide image and automatic visibility
when monitoring pauses/starts. This is foreground Phase 4 UI work.

## Changed files and behavior

- `src/vop/dashboard.py`: native accessible image disclosure per camera, with
  Show image / Hide image labels. Initial open state follows existing monitoring
  controls. Metadata checks detect a monitoring transition and open/close the image.
  Manual choices persist through unchanged polls until monitoring changes or reload.
  Answer disclosures are independent and are not replaced by image updates.
- Hidden panels keep monitoring metadata checks but stop image downloads and preview
  keepalive requests. Existing leases expire within 15 seconds after the last renewal;
  another tab can keep the shared decoder alive. Pending downloads can complete but
  decoding never reopens a hidden panel or replaces its image while hidden.
- Keep decoded image swaps, masks, role checks, green/amber rings, source settings,
  inference scheduling and retained evidence unchanged. Paused images start without
  a pixel URL; a no-JavaScript link can open an existing still when available.
- `tests/test_observe_images.py`: two-camera initial visibility, native labels,
  no initial hidden-image request and existing authenticated/masked read checks.
- `tests/test_observe_image_refresh.py`: Node DOM harness verifies automatic pause/
  resume visibility, manual overrides, no hidden image/lease requests, hidden-tab
  pause, and hiding during decode without reopening or advancing the displayed ID.
- README and CHANGELOG describe the control, default state and lease behavior.

## Commands and results

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_image_refresh.py tests/test_observe_images.py tests/test_live_previews.py tests/test_ui_modes.py`:
  14 passed in 13.75s before the initial hidden-image placeholder refinement.
- Final targeted `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_image_refresh.py tests/test_observe_images.py tests/test_live_previews.py tests/test_camera_answer_groups.py tests/test_observe_answer_refresh.py`:
  15 passed in 6.72s.

- `.\.venv\Scripts\python.exe -m pytest -q`: 356 passed, 4 skipped in 91.69s.
- `git diff --check`: passed.
- Authenticated managed restart: HTTP 202 and a new instance ready. Camera enabled,
  image-saving and sampling-interval settings preserved; observations 10603 -> 10608
  while existing monitoring drained/resumed. No private images/credentials inspected.

CI outcomes are tracked with this change's PR.

## Limits and next acceptance

Tests use explicit synthetic frames/fake decoders and a Node DOM harness. No actual
browser visual check, live camera test, model download or GPU benchmark was performed.
No model/runtime changes; approved historical model revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Manual visibility is per displayed page, not a saved camera setting. Reload resets it
from monitoring state. Automatic visibility checks follow the existing 0.2-second
metadata loop plus request/decode time; no measured latency guarantee is made.
A manual Show on a paused camera enables its transient preview without starting
question monitoring. Hidden previews can take up to 15 seconds to close and another
visible tab can keep them active. Monitoring and answer updates continue normally.

Refresh Observe once. Confirm Pause hides the picture, Start monitoring shows it,
manual Show/Hide works per camera and open answer panels keep updating. Continue
Phase 4 manual acceptance; Phase 5 remains unauthorised. Do not auto-merge.
