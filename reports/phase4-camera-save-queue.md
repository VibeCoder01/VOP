# Phase 4: camera saves during monitoring

22 October 2026. Owner reported Add camera failing with an observation-busy error.

## Root cause and changed files

- `src/vop/integration_ui.py`: camera create/edit used a nonblocking observation lock
  after writing protected account/address values. An active observation rejected the
  save and could leave new protected values with the previous source configuration.
  Camera saves now wait for the lock in a worker thread, then write protected values
  and configuration while holding it. Finally release the lock even if storage fails.
  Camera forms explain the wait; the existing Working button indicates submission.
- `src/vop/browser_auth.py`: both `/cameras/save` and `/integration/camera` also wait
  for browser mutation admission instead of returning 429 when another request owns it.
  Auth, role, origin, CSRF and Configure-mode checks still precede waiting. Other
  mutation/API admission behavior is unchanged. This is request-scoped waiting, not
  an unattended background job or a change to inference scheduling.
- `tests/test_camera_save_queue.py`: actual thread/lock contention for new and edited
  cameras through both routes. Assert no secret/source changes while waiting, health
  remains responsive, controls/observations unchanged, no camera acquisition on save,
  and retry after protected-storage failure releases the locks.
- README and CHANGELOG document waiting, monitoring and the separate camera test.

## Commands and results

- `.\.venv\Scripts\python.exe -m compileall -q src/vop`: passed.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_camera_save_queue.py tests/test_phase4_worker.py tests/test_metric_help_camera_names.py`:
  39 passed in 11.79s. Concurrency fixture cleanup was hardened afterwards; the full
  suite below exercises that final version.
- `git diff --check`: passed.

- `.\.venv\Scripts\python.exe -m pytest -q`: 356 passed, 4 skipped in 86.35s.
- Authenticated managed restart: HTTP 202 and a new instance ready. Camera enabled,
  image-saving and sampling-interval settings preserved; observations 9396 -> 9400
  while existing monitoring drained/resumed. No camera credentials or imagery read.

CI outcomes are tracked with this change's PR.

## Limits and next acceptance

Offline fixtures use explicit synthetic frames, fake credentials and no camera
connections. No live camera test, model download, GPU benchmark or browser visual
validation was performed. Model/runtime unchanged; historical approved revision is
`051bcc464b01b9f92942b364d9586b0ef5912432`.

A save may take as long as the current observation/configuration request. Keep the
form open while it shows Working. Saving itself does not open a camera or start
inference; Test camera retains its existing next-available-slot behavior. Storage
errors are still reported; waiting does not suppress them or promise cross-file
transaction rollback.

Retry Add camera after refreshing the updated form, keeping monitoring enabled.
Continue Phase 4 manual acceptance; Phase 5 remains unauthorised. Do not auto-merge.
