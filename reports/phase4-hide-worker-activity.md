# Hide internal activity from Observe — 20 October 2026

Remove the Observation in progress/shared-worker explanation from camera controls.
Keep Monitoring is running, real setup warnings, scheduled-observation acknowledgements
and the existing observation controls. Internal activity does not replace camera status.
No scheduling, permission, inference or storage behavior changed.

Changed files: `src/vop/dashboard.py`, `tests/test_operator_workflow.py`, `README.md`,
`CHANGELOG.md` and this report.

Validation: `.\.venv\Scripts\python.exe -m pytest tests/test_operator_workflow.py tests/test_ui_modes.py -q`
returned 21 passed in 7.61 s. The existing held-capture regression now also verifies that
neither the removed heading nor shared-worker text appears, while starting/pausing another
camera and scheduling its observation still works. `git diff --check` passed.

Applied through the authenticated restart endpoint. New-instance health succeeded and source
enabled/image-saving/interval controls were preserved. Existing monitoring drained/resumed;
answer count increased from 1876 to 1878. No new manual camera, GPU or model test was run;
offline tests use synthetic/mock inputs. No dependencies, schema or model revision changed;
historical approved d1 revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Refresh Observe to load the change. Existing in-memory one-shot request restart limitations
remain documented in the camera-turns report. Continue the Phase 4 pilot; Phase 5 remains
unauthorised. CI results must be checked separately before merging.


## CI correction

The Windows push job 118903946548 on revision 5073572 failed in
`test_input_history_delete_keeps_configuration_other_input_and_clears_gaps`: history deletion
returned HTTP 429 instead of 200. The Windows PR job and both Ubuntu jobs on the same
revision passed. The deletion tests used TestClient lifespan, which started alert evaluation
in the background. Its lock could be held at deletion time; production correctly rejects
that contention rather than deleting concurrently.

Disable automatic sampler/alert startup in this test module, where captures and evaluations
are already invoked explicitly. Keep the tests that deliberately hold pipeline and alert
locks and assert 429. No production guard is weakened; no app restart is needed for this
fixture-only correction. Additional changed files: `tests/test_history_deletion.py`, README,
CHANGELOG and this report.

- `.\.venv\Scripts\python.exe -m pytest tests/test_history_deletion.py -q`: 9 passed in 4.38 s.
- A Python subprocess loop ran the failed test in 15 separate pytest processes: all 15 passed.
  Exact pytest invocation per process: `.\.venv\Scripts\python.exe -m pytest tests/test_history_deletion.py::test_input_history_delete_keeps_configuration_other_input_and_clears_gaps -q`.
- `.\.venv\Scripts\python.exe -m pytest -q`: 312 passed, 4 Linux-only skips in 78.01 s.
- `git diff --check`: passed.

No hardware, camera, model or GPU checks were needed or run for this test correction.
Model revision and measurements are unchanged. Continue the Phase 4 pilot after checks pass;
Phase 5 remains unauthorised.
