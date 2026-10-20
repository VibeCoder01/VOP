# Restore monitoring controls in View mode — 20 October 2026

The View/Configure split incorrectly treated Start/Pause monitoring as configuration.
Restore these operating controls on Observe in View mode for authenticated operators,
including starting a paused input. Configuration of intervals, connections, questions,
image saving and deletion remains in Configure mode. Existing viewer and CSRF protection
is retained. The monitoring implementation, saved interval, pause behavior and worker
cleanup are unchanged; middleware now permits the existing monitoring action in View mode.

Changed files: `src/vop/browser_auth.py`, `src/vop/dashboard.py`,
`tests/test_operator_workflow.py`, `tests/test_ui_modes.py`, `README.md`,
`CHANGELOG.md` and this report. This corrects the Phase 4 UI; no new phase is started.

Validation on Windows:

- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_modes.py tests/test_operator_workflow.py -q`:
  19 passed in 5.60 s. The monitoring regression switches to View mode, starts a disabled
  synthetic input, checks Start/Pause labels, pauses and resumes the saved 47-second interval,
  verifies manual capture remains enabled, checks pause persistence after app recreation,
  rejects missing CSRF and denies viewer controls. The sampler is stopped during the test;
  no live input, worker, model or GPU is invoked.
- `.\.venv\Scripts\python.exe -m pytest -q`: 308 passed, 4 skipped in 64.35 s.
  The skips are Linux-only helper tests on Windows.
- `git diff --check`: passed.

Applied through the normal authenticated restart endpoint. A new process returned health
success; all source enabled/image-saving/interval controls were preserved. Observation
count increased from 1190 to 1193 while existing user-configured monitoring drained and
resumed. This was restart verification, not a new model or camera benchmark. No manual
camera/Antec/GPU test was run, and no new model result is claimed. No dependencies,
schema or model revision changed. Historical approved d1 revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Refresh Observe to load the controls. As before, the automatic desktop workflow exposes
Start/Pause; a manually hosted server without automatic recovery retains its existing UI.
True viewer credentials remain read-only; an operator in View mode can operate monitoring.
Recommend continuing normal Phase 4 pilot use. Phase 5 remains unauthorised.
