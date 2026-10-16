# Observation names and recorded-image guidance — 16 October 2026

Changed files: `src/vop/dashboard.py`, `src/vop/integration_ui.py`, `src/vop/storage.py`,
`tests/test_observation_images_ui.py`, `README.md`, `CHANGELOG.md` and this report.
Supports UI-003/UI-004/UI-005 and NFR-010 within the existing Phase 4 pilot.

Rename the navigation and page titles to Individual Observations and Continuous Observations
(Episodes). Keep existing URLs, records, question versions and measurement rules. Describe
episodes as grouped sampled checks, not continuous video.

Individual and recent-observation lists show View saved image, No image saved, No image
captured, or Operator access required. Saved-image links open the observation's Recorded
image section. Availability is queried with a frame join and a boolean expression rather
than loading image payloads into the observation listing. This is additive metadata in the
existing observation responses; there is no database migration.

The camera page, selected-input observation list, observation detail and capture result show
the current image-saving state and a direct link to its checkbox. Rename the checkbox to
Save images for Individual Observations. Explain the off-by-default policy, one masked still
per capture shared by its answers, temporary previews, future-only setting changes and
independent image deletion/retention. Existing records do not store the image policy at capture
time, so missing-image guidance lists possible causes without inventing which one occurred.
Turning saving off does not delete existing images. Turning it on cannot recover missing ones.
Existing operator-only image permissions remain enforced; viewer image requests still fail.
No user's setting is enabled or otherwise changed automatically.

Windows validation:

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_phase2_browser_storage.py tests/test_history_deletion.py tests/test_separate_setup.py tests/test_ordinal_labels.py`:
  34 passed in 7.81 s.
- Initial focused image UI regression checks: 3 passed in 1.71 s; the subsequent capture-failure
  regression is included in the full suite below.
- `.\.venv\Scripts\python.exe -m pytest -q`: 302 passed, 4 skipped in 50.94 s. The skips are
  Linux-only helper tests on Windows. Tests cover new labels, current settings, no mutation on
  GET, future-only saving, actual synthetic saved-image display, image deletion, viewer denial,
  retained images after disabling saving and capture-failure guidance.
- `.\.venv\Scripts\python.exe tools\phase4_smoke.py`: PASS; explicit mock worker over actual
  loopback HTTP, 3 observations persisted after restart, browser health form and disposable real
  Windows DPAPI check passed. No cameras connected or model weights loaded.
- `git diff --check`: passed.

No camera capture, real-model inference or GPU benchmark was run for this UI change. No model
revision or dependency changed; the existing historical d1 revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`. No new visual browser automation was used;
HTML routes, synthetic image delivery and permissions were checked offline.

Limitations: an absent historical image does not reveal whether saving was off or the image
was deleted. Images remain optional and operator-only. Recommendation: enable image saving
explicitly on selected inputs if future observations need retained images, then review them
in Individual Observations as part of the current pilot. Phase 5 remains unauthorised.
