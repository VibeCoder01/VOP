# Metric help and camera names — 15 October 2026

Changed files: `src/vop/dashboard.py`, `src/vop/integration_ui.py`,
`tests/test_metric_help_camera_names.py`, `README.md`, `CHANGELOG.md` and this report.
Supports the existing UI-003/UI-004 and MET-004 through MET-010 presentation requirements.

Native hover tooltips explain Daily episode counts / choice dwell, Occupancy, Coverage,
Covered time, Valid samples, Unobserved gap and Estimated duration. Further definitions cover
Active conditions, Unknown conditions, Configured sources, Episodes recorded, Episodes,
Estimated active time, Episode rate, Unobserved time and the input/condition states. Labels
use dotted underlines and keyboard focus; accessible names contain the same explanations.
Definitions follow the existing replay rules. No metric calculation changes.

The camera editor accepts a display name. A separate Rename page works for RTSP and USB
cameras without reading credentials. Names are persisted in existing settings storage and
restored at startup, including for configured inputs. IDs, saved connection references,
questions and history remain unchanged. Rename does not change source controls or start
capture. The connection editor reads the model from the saved profile independently of
the display name. Input filters and latest answers show names alongside stable IDs.

Validation commands and observed results:

- `.\.venv\Scripts\python.exe -m pytest -q tests/test_metric_help_camera_names.py tests/test_separate_setup.py tests/test_phase4_worker.py`:
  39 passed in 10.13 s.
- `.\.venv\Scripts\python.exe -m pytest -q`: 285 passed, 4 skipped in 43.47 s;
  skips are Linux-only helper tests on Windows.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_metric_help_camera_names.py`:
  4 passed in 1.67 s after broadening name restoration to configured RTSP inputs.
- `.\.venv\Scripts\python.exe tools\phase4_smoke.py`: PASS. Explicit mock worker over
  actual loopback HTTP; 3 observations persisted after restart; browser health form and real
  disposable Windows DPAPI check passed. Camera not connected; model weights not loaded.
- `git diff --check`: passed.

Offline browser-route checks cover tooltip text/accessibility attributes, generated camera
names, independent model selection, escaped display names, RTSP/USB restart persistence,
unchanged questions/controls/connection references, no secret access during rename, validation,
viewer denial, CSRF rejection and capture-lock rejection. No new browser visual inspection,
camera test, GPU benchmark or model inference was performed for this change. No dependency,
schema or model revision changes. Existing approved d1 revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Deployment limitation: the local app was actively monitoring (one scheduled source and an
in-flight operation), so it was not restarted. The new UI becomes available after its next
normal restart. No user camera was renamed and no monitoring settings were changed.
Native hover timing depends on the browser; assistive labels provide the same definitions.

Recommendation: review these usability changes in the Phase 4 pilot after the next normal
restart. Phase 5 remains unauthorised.
