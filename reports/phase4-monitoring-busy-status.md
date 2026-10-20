# Normal monitoring activity status — 20 October 2026

Observe classified the shared capture lock as a setup dependency. Each normal scheduled
capture therefore changed the page from Ready to try to Needs attention. Remove the
transient lock from configuration prerequisites and display Observing… as neutral activity
instead. Disable Observe now while the slot is occupied; keep Pause monitoring enabled.
Real missing prerequisites still take precedence and retain their remediation links.

A stale manual-capture request returns an Observation in progress page without starting
another observation or contacting a remote worker for a health check. The pipeline still
enforces its one-frame/no-queue lock, including races after rendering. API overload behavior
is unchanged. No inference, acquisition or temporal measurement contracts changed.

Changed files: `src/vop/dashboard.py`, `src/vop/ui_readiness.py`,
`tests/test_operator_workflow.py`, `README.md`, `CHANGELOG.md` and this report.

Windows validation:

- `.\.venv\Scripts\python.exe -m pytest tests/test_operator_workflow.py tests/test_ui_modes.py tests/test_phase4_worker.py -q`:
  50 passed in 14.15 s. A synthetic fixture holds the capture lock and checks neutral status,
  disabled manual capture, enabled Pause, no new observation on a stale capture request,
  continued missing-question warnings, successful pause and idle-state recovery. The sampler
  is stopped; no camera, real worker, model or GPU is used in this regression.
- `.\.venv\Scripts\python.exe -m pytest -q`: 309 passed, 4 skipped in 59.41 s.
  The skips are Linux-only helper tests on Windows.
- `git diff --check`: passed.

Applied using the authenticated restart endpoint. A new process returned healthy, with
all source enabled/image-saving/interval controls unchanged. Recorded answer count increased
from 1438 to 1440 while existing user-configured monitoring drained and resumed. This is
restart verification, not a new hardware benchmark or model validation. No manual live-camera,
Antec or GPU test was run. No dependencies, schema or model revision changed; historical
approved d1 revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Limitations: the status describes the shared observation slot, which can be occupied by
another input. Pause prevents further scheduled observations; an in-flight one can finish.
Recommended next step is normal Phase 4 monitoring use. Phase 5 remains unauthorised.
