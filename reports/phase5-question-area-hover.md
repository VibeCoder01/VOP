# Phase 5: Observe question-area hover

Version 0.6.19. Full Observe answer rows with include/exclude areas are focusable and carry current normalized region metadata. Delegated hover/focus draws an SVG guide only on that camera's Last processed image. Include is green, exclude red/dashed, with an identifying text legend and exclusion-priority explanation. No areas means no overlay. Nothing is fetched or captured by this script.

Coordinates account for contain-fit image scaling and horizontal/vertical letterboxing. On resize or image load the guide redraws; mouse/focus leave, closing the answers, hidden document and page exit clear it. Mutation observation follows replaced answer rows during polling without keeping obsolete area coordinates. Guides never alter image bytes, evidence, live previews or inference. The legend says current configured areas rather than claiming historic preprocessing metadata.

Changed files: src/vop/question_area_preview.py (new browser script); src/vop/dashboard.py (row metadata, script route/loading and scoped SVG styles); src/vop/browser_auth.py (authenticated View-mode access to the read-only script); tests/test_question_area_preview.py (new); README.md; CHANGELOG.md; pyproject.toml; this report.

Validation: `.venv/Scripts/python.exe -m pytest -q tests/test_question_area_preview.py tests/test_camera_answer_groups.py tests/test_observe_answer_refresh.py tests/test_observe_image_pairs.py` — **14 passed in 16.72s**. Tests use offline TestClient and Node fake DOM: current policies in initial/refreshed rows, keyboard affordance, no marker for unconfigured rows, authenticated View-mode script access, exact letterbox rectangle geometry, camera target isolation, mouse/focus clearing and hidden-image/document handling. Existing answers/images polling regressions included. No live browser visual inspection.

`.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .` installs 0.6.19; `git diff --check` checked before commit. No camera, new model run/weights, GPU benchmark or physical/email/audio/SMS action was used. Existing model revision and measurements unchanged. Service not restarted; launch Start VOP to load the update. CI pending at PR creation.

Limitations: Full Observe answers only; images must be shown and a processed image available. Grid lights do not carry this overlay. Shows current configured question include/exclude areas, not historic regions. Camera privacy masks remain baked into the image; ROI is separate. Continue Phase 5 review/CI; Phase 6 is not started.
