# Setup navigation and permanent question deletion — 21 October 2026

Configure navigation now contains only Cameras, Engines, Questions and Settings.
Individual Observations, Continuous Observations (Episodes) and Trends remain in View
navigation. Remove the camera history shortcut and the duplicate recent-observations table
from the Inputs setup page. Existing read URLs remain valid; administrative history/image
deletion remains reachable through Settings → Manage saved data.

Removed questions now offer Delete permanently… next to Restore. The GET opens a read-only
confirmation showing the question text and effect. POST requires operator permission,
Configure browser mode, same-origin CSRF and the expected question version. Only a currently
removed question can be deleted; active/restored/stale confirmations are rejected. Capture
and alert-processing locks protect the change. The deletion is audited.

Permanent deletion removes the question from both active and removed configuration listings
and makes app restoration impossible. A persisted deleted-question marker filters its
configuration, while its disabled version pointer, immutable definitions/policies, recorded
answers, images and episodes remain unchanged. Keeping the historical version pointer is
necessary to preserve superseded episode states during replay. The existing removal marker
also prevents the original seed configuration from resurrecting a deleted question. An export
omits it; a backup taken after deletion retains this state. IDs stay reserved, and automatic
question IDs consider all historical IDs so replacement questions get an unused ID.

Changed source: `src/vop/dashboard.py`, `src/vop/integration_ui.py`, `src/vop/removal.py`,
`src/vop/storage.py`. Updated tests: `tests/test_ui_modes.py`, `tests/test_removal.py`,
`tests/test_observation_images_ui.py`. Also changed README, CHANGELOG and this report.
No schema migration, dependency or inference contract change.

Windows validation:

- `.\.venv\Scripts\python.exe -m pytest tests/test_removal.py tests/test_ui_modes.py tests/test_observation_images_ui.py -q`:
  16 passed in 17.12 s after the final deletion-marker implementation. Tests cover removed-only
  confirmation, read-only GET, stale versions, CSRF, viewer/View-mode denial, busy capture/alert
  locks, restored-question rejection, both configuration listings, reserved/generated IDs,
  audit, unchanged answers and events across restart, and backup/restore after deletion.
  The history test includes multiple question versions and checks foreign-key integrity.
- `.\.venv\Scripts\python.exe -m pytest -q`: 315 passed, 4 skipped in 128.08 s. Skips
  are Linux-only helper tests on Windows. A prior focused test was corrected to use the
  existing restore function's config-file return value; configuration-page expectations
  were updated for setup-only navigation.
- `.\.venv\Scripts\python.exe tools/phase2_smoke.py`: PASS; synthetic input, explicit mock,
  native session/CSRF forms, six views, replay, viewer image denial 403, deleted image 404,
  and 21 recorded answers persisted after process restart. No cameras connected.
- `git diff --check`: passed.

Applied via authenticated app restart. A new instance returned healthy and all source
enabled/image-saving/interval controls were preserved. Existing user-configured monitoring
drained/resumed; answer count increased from 3460 to 3462. No real user question was deleted:
the new destructive path was tested only with disposable synthetic/mock data. No manual
camera, Antec, real-model or GPU validation was run; no new benchmark is claimed. Historical
approved d1 revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`.

Limits: Delete permanently discards restorable configuration, not historical records. Old
question IDs stay reserved; historical definitions remain to interpret saved results. A
backup from before deletion can still restore its earlier setup. To erase observations or
images, use the separate saved-data deletion tools. Continue the authorised Phase 4 pilot;
Phase 5 remains unauthorised.
