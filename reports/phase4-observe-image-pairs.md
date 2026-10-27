# Phase 4 — paired live and processed images

Date: 27 October 2026

## Behavior and changed files

Observe now displays compact live/current and last-processed source images side by
side, with responsive stacking. Both enlarge on hover or keyboard focus to a
viewport-bounded 800 × 440 image, matching the former display size. Fixed preview
position and reserved thumbnail stages avoid layout shifts. Existing green/amber
monitoring rings and automatic show/hide behavior apply to the pair.

- `src/vop/pipeline.py`: publish a separate completed, privacy-masked source preview
  only after `Store.save` commits. The transient per-source slot is independent of
  in-flight/test previews. Preview clearing, deletion and retention clear both.
  A short preview mutation lock and identity check ensure a preview cleared during
  result completion cannot be republished after deletion; no camera I/O holds it.
- `src/vop/answer_images.py`: resolve the common frame of the actual enabled answer
  observation IDs using bounded metadata joins. Match the completed cache or exact
  retained frame only. Missing, different or frameless answers do not substitute an
  unrelated image. Frame path components are URL-quoted; no model imports or shared
  filesystem assumptions are introduced.
- `src/vop/dashboard.py`: paired layout, hover/focus styling, frame-pinned protected
  image endpoint and answer-response provenance headers. Image availability affects
  the ETag so clearing/deletion changes the display even without a new answer.
  If a capture commits during rendering, resolve image provenance again from the
  actual rendered rows and omit the earlier revision's ETag for that response.
  Decode the processed image before replacing the corresponding answer HTML;
  failures hide stale pixels, keep current answers and retry. Bound image decoding
  to five seconds so it cannot indefinitely hold answer refreshes. Hidden images
  do not download; 304 responses can retry or load the image when reopened.
- `src/vop/browser_auth.py`: authenticated read route for processed images in View
  mode. Operator checks on GET and HEAD retain the existing image-access boundary.
- `tests/test_observe_image_pairs.py`: six synthetic tests cover an in-flight
  capture, privacy-masked pixels, source/answer frame pinning, no substitution of an
  older retained image, cache loss, exact retained fallback, deletion invalidation,
  viewer denial, test-preview isolation, and a capture committing during rendering.
  A post-commit clearing test proves deleted image bytes cannot be republished.
  Node checks cover atomic image/answer updates, decode failure/timeout, retry after
  304, hidden/reopened images and hiding during decode, without page reloads.
- `tests/test_observe_images.py`: update the shared plural Show/Hide images label.
- `README.md`, `CHANGELOG.md`, this report: user behavior and limits.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_images.py tests/test_observe_image_refresh.py tests/test_observe_answer_refresh.py tests/test_camera_answer_groups.py tests/test_loop_efficiency.py`:
  **21 passed in 25.81s** during implementation.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_image_pairs.py tests/test_camera_answer_groups.py tests/test_observe_answer_refresh.py`:
  **11 passed in 7.99s** after adding the render-race check.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_image_pairs.py tests/test_observe_answer_refresh.py tests/test_observe_images.py`:
  **10 passed in 6.27s** with the decode-timeout check.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_observe_image_pairs.py tests/test_observe_images.py tests/test_live_previews.py`:
  **15 passed in 11.72s** after the preview-publication clearing guard.
- `.\.venv\Scripts\python.exe -m pytest -q`: **415 passed, 4 skipped in 162.02s**
  after the preview-publication guard. Skips are the opt-in hardware tests.
- `git diff --check`: passed.
- Managed draining restart: HTTP **202** while an observation was in flight; new
  instance ready, all three source-control tuples preserved, observation count
  **17666 → 17667**. Existing monitoring finished its observation and resumed;
  no manual camera/model test or capture was requested.

## Privacy, hardware and limits

The source frame is already privacy-masked; an ROI question can receive a crop of
that source, so this is not a claim that every question receives identical image
bytes. No additional persistent image storage is enabled. Completed previews are
one per configured source (32-input configuration limit); normal completed/current
previews share the same immutable byte object until a newer capture/test replaces
the current preview. They are lost on restart unless the exact frame was saved.

Image/frame IDs are matched explicitly rather than selecting the newest image by
timestamp. A missing exact frame is a visible limitation, not an invented match.
The current pair updates through existing answer polling (0.2 seconds while answers
are shown; 1 second while hidden); the independent live loop retains its 5 fps target.
No actual camera-to-screen latency measurement or visual browser/screenshot QA was
performed. Hover/focus presentation was checked in source; endpoint and script
behavior used disposable synthetic histories and colored pixels only.

No live imagery was inspected, no real camera/model/GPU test or download ran, and
no live records were deleted. Historical Liquid revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`. Next Phase 4 acceptance is to refresh
Observe, compare both timestamps/answers, and try hover or keyboard enlargement on
intended user cameras. Phase 5 remains unauthorised; do not auto-merge.
