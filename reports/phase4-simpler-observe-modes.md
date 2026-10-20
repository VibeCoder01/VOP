# Simpler Observe and mode navigation — 20 October 2026

Implement the six requested UI refinements within the authorised Phase 4 pilot:

- Hide the one-shot Observe now/Capture once form when that camera has continuous monitoring
  enabled. Keep session status and Pause; one-shot controls return after pausing. Existing
  scheduling endpoints remain valid for already-submitted requests.
- Rename the removed-camera section to Retired Cameras. Retirement, restoration and stored
  flags are unchanged.
- Omit retired inputs from the Individual Observations filter. Do not delete or hide existing
  records from All inputs or invalidate old history links. Restored cameras return to the filter.
- Omit Observe from Configure navigation, remove camera/engine Observe shortcuts, point the
  brand to Cameras in Configure mode and redirect its browser root to Cameras. Bearer API
  behavior remains unchanged. The deletion warning now directs users to the sidebar switch
  to pause monitoring in View mode, avoiding a dead Configure-mode Observe link.
- Keep one sidebar mode-switch form per page, consistently labelled with its target: Configure
  mode or View mode. Remove the duplicate switch from the setup-required page. Keep CSRF
  and role checks; viewer credentials cannot elevate.
- Remove Recent Individual Observations from Observe. The dedicated Individual Observations
  page retains those records. The separate Inputs configuration page retains its existing table.

Changed source: `src/vop/dashboard.py`, `src/vop/integration_ui.py`,
`src/vop/history_deletion.py`. Updated tests: `tests/test_ui_modes.py`,
`tests/test_operator_workflow.py`, `tests/test_history_deletion.py`,
`tests/test_metric_help_camera_names.py`, `tests/test_title_camera_names.py`,
`tests/test_ordinal_labels.py`, `tests/test_phase4_worker.py`. Also changed
`tools/phase2_smoke.py`, README, CHANGELOG and this report. Older tests now explicitly use
View mode when checking Observe; their configuration helpers still enter Configure mode.

Windows validation commands/results:

- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_modes.py tests/test_operator_workflow.py tests/test_history_deletion.py tests/test_title_camera_names.py tests/test_ordinal_labels.py tests/test_metric_help_camera_names.py tests/test_phase4_worker.py -q`:
  75 passed in 25.98 s.
- `.\.venv\Scripts\python.exe -m pytest -q`: 313 passed, 4 skipped in 81.68 s.
  Skips are Linux-only helper tests on Windows. The initial run identified seven tests
  expecting the old Configure root/monitoring controls; their UI expectations were updated.
- `.\.venv\Scripts\python.exe tools/phase2_smoke.py`: PASS; synthetic input, explicit mock,
  native browser-session forms, replay, six views, viewer image denial 403, deleted-image
  denial 404 and 21 answers retained after process restart. The old smoke assertion expected
  Observe after entering Configure; it now checks Observe before switching and Cameras after.
- `.\.venv\Scripts\python.exe -m pytest tests/test_ui_modes.py tests/test_history_deletion.py -q`:
  13 passed in 12.68 s after the final retirement-filter and pause-guidance refinements.
- `git diff --check`: passed.

Tests verify a single switch on both normal pages and setup-required prompts, target labels,
Configure navigation/brand/root, no duplicate history section even with recorded results,
no one-shot form during monitoring, and retired/restored camera filter entries. History
remains stored and old links remain valid. Test captures are synthetic/mock only.

Applied with the authenticated restart endpoint. A new process returned healthy; all source
enabled/image-saving/interval controls were preserved. Existing monitoring drained/resumed;
answer count increased from 2701 to 2703. No new manual camera, model, Antec or GPU test was
run. No dependencies, database schema, capture scheduler or model revision changed. Historical
approved d1 revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Refresh the dashboard to load the new shell. Retired history remains visible in All inputs
by design, but retired inputs have no filter option. Existing in-memory one-shot request
restart limits still apply. Continue normal Phase 4 pilot use; Phase 5 is unauthorised.
