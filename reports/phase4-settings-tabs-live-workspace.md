# Phase 4: Settings tabs and live workspace cleanup

21 October 2026. User-requested usability work within the Phase 4 pilot.

## Changed files and behavior

- `src/vop/release_ui.py`: six server-rendered Settings tabs: Notifications, Rules,
  Export, Configuration and backup, Retention and Audit. Camera/question names,
  severity, existing rules, condition, status, delivery, export format, timezone and
  common retention windows use dropdowns. New rule IDs are automatic when blank.
  UTC date pickers normalize input before filtering/export. Rule forms still accept
  existing source/question API fields. Viewer write/configuration guards remain.
  Remove the MOCK alert banner; offline fixture alerts retain a synthetic label.
- `src/vop/dashboard.py`: Settings navigation opens the tabbed area. Remove the
  shared filter-field bottom margin that displaced action buttons; add responsive
  form-grid and tab styles. Other filter rows receive the alignment correction too.
- `src/vop/live_workspace.py`: transactional, idempotent removal of test sources,
  their definitions/policies/controls/rules, test runs/images/answers, test alerts
  and deliveries, presets, saved test engines, and source-specific test audit entries.
  Real camera history retains timestamp-only gaps where synthetic answers were
  removed. Real source controls, engine profile, questions, observations and alerts
  are preserved. Deletion triggers are temporarily suspended only inside the
  transaction and restored; real immutable versions are not edited or deleted.
  Failure rolls back both records and trigger changes.
- `src/vop/service.py`, `tools/run_dashboard.py`: select live workspace for the normal
  Start VOP launch with --allow-live-sources, before loading configuration. Filter
  sample sources so they cannot return. Preserve the real selected worker; default
  to the approved Antec profile only if no real worker was selected. Startup alone
  does not load a model or initiate a camera test.
- `src/vop/integration_ui.py`: live engine setup offers real AI workers only; reject
  test-engine creation through both current and legacy form routes.
- `src/vop/reliable.py`: use Yes/No in the rule validation message.
- `tests/test_settings_tabs.py`, `tests/test_live_workspace.py`: distinct sections,
  named choices, date normalization, generated rule IDs and paused status, retention
  permissions, preservation of real fixture data/alerts/deliveries, removal of test
  entries, restart idempotence, trigger rollback and live engine restrictions.
- README and CHANGELOG: runbook, cleanup behavior and limits.

## Commands and results

- `.\.venv\Scripts\python.exe -m compileall -q src/vop`: passed.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_phase3_release.py tests/test_display.py tests/test_ui_modes.py tests/test_phase4_worker.py`:
  65 passed in 26.21s.
- New Settings/live-workspace tests: 4 passed in 2.32s after correcting test fixture
  mode setup and a SQL placeholder count. These were test-only setup errors.
- `.\.venv\Scripts\python.exe -m pytest -q`: 335 passed, 4 skipped in 106.71s.
- Final cleanup/audit/UI-mode regression command:
  `.\.venv\Scripts\python.exe -m pytest -q tests/test_live_workspace.py tests/test_settings_tabs.py tests/test_ui_modes.py`:
  8 passed in 10.39s.
- `.\.venv\Scripts\python.exe tools/restart_smoke.py`: PASS; fresh interpreter
  and instance, retained operator key and 3 synthetic observations, launcher replaced
  old instance, loopback only. Cameras not connected and model weights not loaded.
- `git diff --check`: passed.

## Actual application

Authenticated managed restart returned HTTP 202 and a new instance. Removed one
remaining test input. All 5,842 pre-existing real observation IDs were verified as
preserved; total observations increased 5,842 -> 5,844 while work drained/resumed.
There were no existing real alerts to preserve. All real camera enabled/evidence/
interval controls and the selected real engine profile were verified unchanged.
No new live-camera connection test, inference benchmark, GPU test or model download
was initiated. Existing saved monitoring resumes normally.

## Limits and recommendation

Backup archives, old exports and repository offline fixtures are not erased. Explicit
non-live development launches retain clearly labelled synthetic tools for offline
validation. Retention offers common periods; legacy/API duration inputs remain
compatible. Backup and restore still require the documented offline tool; these
were reorganized, not replaced with a new backup system. Date pickers are explicitly
UTC. No new model measurements were made; the historical approved revision remains
051bcc464b01b9f92942b364d9586b0ef5912432. No hardware feasibility claims are added.

Continue Phase 4 user acceptance of Settings and real-only workspace behavior.
Phase 5 remains unauthorised; do not auto-merge.
