# Phase 4: Observe images and camera-test layout

22 October 2026. User-requested Phase 4 usability correction.

## Changes

- `src/vop/integration_ui.py`, `dashboard.py`: camera-test image/content and footer
  are separate blocks. Test camera again and Back to camera are grouped in a wrapping
  action row below the picture; Back to camera is a consistently styled button.
- `pipeline.py`: bounded per-camera masked/downscaled preview cache (one per configured
  input, at most 32). Capture publishes the preview before inference finishes. Keep
  the last acquired image while paused and when subsequent acquisitions fail.
  One camera no longer replaces another camera's latest preview.
- `dashboard.py`, `browser_auth.py`: Observe image cards with green monitoring and
  amber paused rings plus textual labels and capture timestamps. Authenticated
  metadata-only HEAD polling every five seconds while visible updates monitoring
  state and fetches only changed images. Reads never acquire camera frames or invoke
  inference. Missing images have an actionable placeholder. Native initial image
  rendering works without JavaScript; automatic updates require JavaScript.
- `storage.py`: latest saved image lookup for restart fallback, labelled Latest saved
  image so it is not confused with a new acquisition. Preview routes remain
  operator-only with no-store headers; viewer access stays denied.
- `history_deletion.py`, `removal.py`, `dashboard.py`: clear the correct camera/frame
  from the multi-camera cache after deletion or retirement. Retention still clears
  all temporary previews. Removing one camera does not clear other cameras' images.
- `tests/test_observe_images.py`: multi-source isolation, masked pixels, green/amber
  state, disabled-monitoring image persistence, no extra capture, no retained evidence
  when saving is off, saved fallback, deletion, permissions and camera-test footer.
- `tests/test_observe_image_refresh.py`: Node browser-script unit harness checks new
  frames, unchanged-frame requests, captions, green/amber transitions, no-image state
  and hidden-tab polling pause. No real browser, camera or GPU is used by this harness.
- README and CHANGELOG describe the behavior and storage limitations.

## Verification

- `.\.venv\Scripts\python.exe -m compileall -q src/vop`: passed.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_phase4_worker.py tests/test_operator_workflow.py tests/test_history_deletion.py tests/test_question_data_deletion.py`:
  60 passed in 23.87s.
- Initial image/format regressions: 3 passed in 2.82s.
- Full offline suite: 339 passed, 4 skipped, one test failed because the new Node
  test harness lacked its closing brace. Application JavaScript was unaffected.
  Fixed the harness, passed the isolated check (1 passed in 1.22s), then reran final
  affected tests with the corrected harness.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_images.py tests/test_observe_image_refresh.py tests/test_question_data_deletion.py tests/test_history_deletion.py`:
  16 passed in 16.33s.
- `.\.venv\Scripts\python.exe tools/phase4_smoke.py`: PASS; explicit mock worker
  over actual loopback HTTP, three synthetic observations persisted after restart,
  disconnect behavior and real Windows DPAPI checked. Cameras not connected and
  model weights not loaded.
- Final HEAD metadata/header and image-script regressions: 4 passed in 10.59s.
- `git diff --check`: passed.

## Application and limits

Applied using authenticated managed restart: HTTP 202 and a new instance, unchanged
camera enabled/evidence/interval controls, observation count 6414 -> 6416 while
existing monitoring drained/resumed. No new live camera connection test or GPU
benchmark was initiated. No model download or new model measurements. Historical
approved model revision remains 051bcc464b01b9f92942b364d9586b0ef5912432.

Temporary images are memory-only. Restart loses them; a retained image is used when
available. If saving was off and no saved image exists, another explicit observation
or existing monitoring must acquire one. Paused cameras are never captured merely
because somebody opens Observe. Image saving and historical retention settings are
unchanged. Rings show enabled continuous monitoring, not connection health or proof
of uninterrupted capture. Automatic refresh is bounded to five seconds and pauses
when the tab is hidden. This is image inspection, not live video streaming.

Continue Phase 4 user acceptance of the layout and Observe imagery. Phase 5 remains
unauthorised. Do not auto-merge.
