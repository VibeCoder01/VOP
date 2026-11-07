# Phase 5: Sampling summary camera names

Version 0.6.22. The Observe sampling summary uses each source's configured name, falling back to its ID when blank, for both stopped and interval text. No capture, inference, scheduling or controls change.

Changed: src/vop/dashboard.py, pyproject.toml, README.md, CHANGELOG.md, this report. No new test for this display substitution.

`.venv/Scripts/python.exe -m pytest -q tests/test_observe_camera_selection.py` — 2 passed in 6.37s. `git diff --check` passed. Editable install: `.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .` for 0.6.22.

No real camera/model/GPU/device/audio/email/SMS tests or new measurements. Service not restarted; Start VOP loads updated code. Live appearance and CI unverified. Continue Phase 5 review/CI; no Phase 6 work.
