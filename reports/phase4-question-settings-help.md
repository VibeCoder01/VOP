# Phase 4 — advanced question settings help

Date: 24 October 2026

## Change and files

- `src/vop/dashboard.py`: explanatory text for every field in the two advanced question
  groups, with `aria-describedby` links. Explain threshold direction/score semantics,
  consecutive confirmation counts and delay tradeoffs, resume/split/hold gap policies,
  maximum gap versus capture frequency, ROI coordinates/example and enabled status.
  Add a direct link to the camera observation form. Explain its interval as a per-camera
  target covering all enabled questions, with zero pause and processing/retry delays.
- `src/vop/integration_ui.py`: clarify the interval purpose on the camera detail page.
- `README.md`, `CHANGELOG.md`, this report: usage and evidence.

## Validation

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_phase2_controls.py tests/test_metric_help_camera_names.py tests/test_separate_setup.py`:
  **24 passed in 12.90s**.
- Source/semantic review against `measurements.py`, `sampling.py`, `preprocessing.py`
  and `inference/liquid_d1.py` confirmed the help describes the existing behavior.
- No new implementation-mirroring tests for explanatory text. Existing controls/type
  visibility, setup and help tests cover the affected form structures.
- `git diff --check`: passed.
- Authenticated managed restart: HTTP 202; new instance ready, source enabled/image-
  saving/interval controls preserved. Observations 28440 -> 28444 during existing
  authorised monitoring. No new manual camera/model test was started.
- CI is tracked in this change's PR.

## Limits and next acceptance

This is explanatory UI text and links only; defaults, validation, scheduling, inference
and episode logic are unchanged. The manual-review policy currently holds Unknown
for that version and has no approval action in this form; help states that choosing
Resume/Split and saving a new version resumes automatic classification.

Offline/synthetic tests only. No new camera connection, image inspection, model
weights, GPU benchmark, user-data deletion or browser visual test was initiated.
Historical approved model revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Refresh the question editor and camera observation form for Phase 4 acceptance.
Phase 5 remains unauthorised. Do not auto-merge.
