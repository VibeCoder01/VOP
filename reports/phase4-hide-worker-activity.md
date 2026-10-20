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
