# Phase 5 automation markers and mask editors — 29 October 2026

## Behaviour

Observe answer rows show an asterisk when a question has linked automations, including
paused/review-needed links. An eight-second, one-Hz pulse begins from the original trigger
timestamp when an automation queues work. Suppressed/old/manual-test jobs do not flash it.
Tooltips identify linkage and direct users to Activity for delivery; no physical delivery
or model-accuracy claim is inferred. Reduced-motion preferences disable the pulse. Client
expiry ends the highlight even if subsequent polling fails, and repeat polling does not
restart it. Marker metadata invalidates the existing ETag without new captures. Source and
recent-job queries use indexes and the eight-second window rather than replaying old jobs.

Configure Questions now has a camera-image rectangle editor: include union, exclude cuts,
individual removal, Undo, Clear and keyboard coordinate entry. It supports 16 rectangles
per type. Camera settings also has a camera-wide privacy editor in the existing form.
Privacy precedes question regions and optional ROI crops for every engine. Complete
preprocessing policies group requests; default empty masks keep existing behaviour. Different
groups share the existing overall inference deadline and may take longer to evaluate.

Question masks persist in immutable QueryPolicy JSON and create new question versions;
linked automations require review/save. Old policy JSON defaults to empty masks. New fields
require VOP 0.6.6 or later. Camera privacy persists for USB and RTSP and applies to future
images only; old saved images are not rewritten. A grab already hides saved privacy areas,
so save and grab again after removing one. A blue outline shows any advanced ROI.

Explicit Grab image requests queue independently/coalesce per purpose. They do not prepare
the model, run inference or write observations/evidence. USB uses the existing live-preview
suspension path. Only privacy-masked, metadata-stripped PNGs enter the temporary editor cache:
one per source, five-minute expiry on access/scheduler tick, token-bound access and existing
operator/Configure/CSRF checks. Page loading never probes cameras. Clear/delete/retire/privacy
changes evict relevant cache entries, and stale callbacks cannot republish or drop newer
requests. Question deletion also removes mask/ROI provenance for that question from shared
results while preserving other questions' typed answers.

## Changed files

New `mask_editor.py` and `automation_markers.py`; existing dashboard, preprocessing,
measurements, pipeline, sampler, service, browser authorization, camera settings, Actions
source index and deletion scrubber. New synthetic/browser-contract tests; existing camera,
answer refresh and sampling tests updated. README, image-mask runbook, changelog and package
version **0.6.6** updated. No frontend framework, dependency or user_version migration added.
The source index is an additive, idempotent Actions index.

## Validation

- `.venv\Scripts\python.exe -m pytest -q`: **497 passed, 6 skipped** in 243.17 seconds
  before the final USB acquisition and request-replacement refinements. Four skips were
  Linux-only remote helpers, two Linux-only Secret Service contracts on Windows.
- Final `.venv\Scripts\python.exe -m pytest tests/test_question_masks.py tests/test_phase2_sampling_roi.py tests/test_mask_editor_browser.py tests/test_automation_markers.py tests/test_unified_camera_settings.py tests/test_observe_answer_refresh.py tests/test_observe_image_pairs.py tests/test_removed_question_bulk.py -q`:
  **65 passed** in 43.36 seconds. Includes pixel-level privacy/include/exclude ordering,
  grouping, validation, new-version/restart persistence, shared-result deletion scrub,
  camera-only queueing, stale tokens, expired/replaced callbacks, independent test purposes,
  USB release, camera privacy save/clear/invalid-input, unchanged credentials, ETag updates,
  marker timing/suppression and existing answer/image refresh contracts.
- Node fake-DOM contracts exercise both question and privacy editors: reversed drag,
  coordinate validation, keyboard Enter, remove/undo/clear, no list rebuild on pointer move,
  explicit-only capture, queued-image polling and decoding. Marker timers are bounded and
  not duplicated. No real browser visual QA or live imagery inspection was performed.
- Follow-up checks after the final index/client-lifecycle refinements:
  `.venv\Scripts\python.exe -m pytest tests/test_automation_markers.py tests/test_actions.py -q`:
  **22 passed** in 9.73 seconds; browser editor contract **2 passed** in 1.27 seconds,
  including page-hide cancellation and late-response suppression.
- `.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .` installed
  **0.6.6**. `git diff --check` passed (Windows line-ending notices are informational).
- Full Windows/Ubuntu CI and activation results will be recorded on the pull request;
  no passing CI or live deployment is presumed here.

No manual camera, microphone, GPU/model benchmark, Tapo action, audio playback, email or SMS
test was run. Existing authorised monitoring may continue independently. The pinned d1 model
revision is unchanged; no new accuracy or performance measurement is claimed. Drawn masks
are rectangles; arbitrary brushes/polygons are not provided. The common Observe source frame
is not a separate per-question masked rendering. Older retained evidence remains unchanged
by future privacy edits. The existing full-history temporal replay cost remains outside this
change. Recommendation: stay in Phase 5 and validate mask selection using explicit UI grabs
and normal owner-triggered observations/automations. Phase 6 is not started. No auto-merge.
