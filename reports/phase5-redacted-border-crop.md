# Phase 5: Crop configured redacted borders

## Behaviour

Version 0.6.26 computes the visible bounding rectangle from configured geometry, never black/dark scene pixels. Apply source privacy, question include union, question excludes, then original-coordinate ROI intersection; crop away only fully hidden outside rows/columns. Internal hidden holes stay black, and disconnected visible areas remain in one bounding rectangle rather than being stitched. A fully hidden question returns no_visible_image without reaching any inference backend. Normal full-redaction previews are a black 1×1 placeholder.

Live previews, source stills and retained/email images show the source privacy crop. Question-specific engine inputs can be different; Engine image beside an answer returns that exact prepared PNG. These are latest-frame-only operator previews, bounded globally to 32 MiB of distinct payloads, never extra persistent evidence. Old/evicted/deleted/replaced inputs return unavailable, with no newer-frame substitution. Endpoints validate question/version/frame provenance and use latest-first indexed lookup. Source/frame identity, timestamp, pixel hash and per-group provider checks remain intact.

Mask editors keep full-frame coordinate grabs; no saved ROI/mask coordinate is rewritten. Run preprocessing metadata records source_crop and per-question question_crops. Area-hover guides clip/remap original coordinates onto the cropped source image. Question deletion removes its crop metadata and clears temporary previews through existing cleanup paths. Old retained images remain unchanged; missing crop metadata means full-frame coordinates.

## Changed files

Production: src/vop/preprocessing.py, src/vop/pipeline.py, src/vop/live_preview.py, src/vop/mask_editor.py, src/vop/answer_images.py, src/vop/dashboard.py, src/vop/browser_auth.py, src/vop/question_area_preview.py, src/vop/history_deletion.py, pyproject.toml.

Tests: tests/test_redaction_crop.py (new), tests/test_question_masks.py, tests/test_live_previews.py, tests/test_question_area_preview.py, tests/test_save_image_action.py, tests/test_email_image.py, tests/test_observe_image_pairs.py, tests/test_loop_efficiency.py, tests/test_observe_images.py, tests/test_phase2_browser_storage.py, tests/test_phase2_sampling_roi.py. Documentation: README.md, CHANGELOG.md, this report.

## Validation

`.venv/Scripts/python.exe -m pytest -q tests/test_redaction_crop.py tests/test_question_masks.py tests/test_live_previews.py tests/test_question_area_preview.py tests/test_save_image_action.py tests/test_email_image.py tests/test_observe_image_pairs.py tests/test_loop_efficiency.py tests/test_observe_images.py tests/test_phase2_browser_storage.py tests/test_phase2_sampling_roi.py tests/test_stage_timings.py tests/test_fast_observe.py` — **95 passed in 69.69s**. Covers geometry versus naturally dark pixels, internal redaction, original ROI coordinates, no-visible-area inference bypass, exact engine PNG access/permissions/cleanup, remapped hover outlines, saved/email frame identity, the one-query answer batch, live previews, stage timings and fast navigation.

After tightening Engine image's cache-first/latest-first lookup: `.venv/Scripts/python.exe -m pytest -q tests/test_redaction_crop.py tests/test_observe_images.py` — **8 passed in 7.51s**.

Full run `.venv/Scripts/python.exe -m pytest -q` — **570 passed, 6 skipped, 4 failed in 374.07s**. The failures were three legacy padded-image/ROI dimension expectations (including one old function loaded before its assertion was changed), and the existing native-answer SQL-prefix assertion after adding its bounded frame-provenance join. All four were updated to preserve the same privacy/provenance and one-query checks under cropping and passed in the final 95-test run. Entire suite not repeated after those expectation updates; final full-suite/CI success is not claimed.

`git diff --check` passed. `.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .` installed 0.6.26. No dependency change, real camera connection, live image inspection, model download/GPU/model benchmark or real email/Tapo/audio/SMS action. All test images and engine results are synthetic; model revision and historical hardware measurements unchanged. Service not restarted; CI/live appearance unverified.

## Limits / next

Future frames only; restart Start VOP and wait for a new observation. The shared source image reflects camera privacy, while exact question-area crops are available through temporary Engine image links. Saved/email image actions continue using the canonical source privacy image; question crops are not retained as separate history. Cache eviction/restart can make an engine input unavailable until a new observation. Cropping may change real model answers/context as intended; real accuracy/performance has not been measured. No automatic camera/automation setting changes or unmasking. Continue Phase 5 review/CI; no Phase 6 work.
