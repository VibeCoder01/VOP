# Full launcher restart and browser restart — 15 October 2026

Changed files: `Start VOP.cmd`, `tools/run_dashboard.py`, `tools/restart_smoke.py`,
`tools/build_release.py`, `src/vop/lifecycle.py`, `src/vop/service.py`,
`src/vop/browser_auth.py`, `src/vop/dashboard.py`, `src/vop/pipeline.py`,
`src/vop/sampling.py`, `tests/test_lifecycle.py`, `tests/test_phase4_worker.py`,
`.github/workflows/offline-tests.yml`, `README.md`, `CHANGELOG.md` and this report.

Start VOP uses `--restart-existing`. Process matching requires this installation's exact
launcher path, Python runtime, account and port. The launcher and its ancestors are excluded
from cleanup, including Windows venv redirectors. Responsive managed instances receive an
authenticated shutdown request. Older versions receive a normal worker-session stop request.
Stale matched processes and their observed descendants are terminated after the grace period;
other applications and instances on other ports are not stopped. A remaining port conflict
produces a remediation message rather than sending a key to an unknown listener.

Operator-only sidebar and Settings forms request a restart, with existing origin and CSRF
checks. Lifecycle requests remain available while capture admission is occupied. The launcher
stops new sampling and pipeline work, drains current HTTP/background work, closes its owned
Antec worker session, then executes a fresh interpreter. Persisted setup and monitoring choices
remain. The same access key is retained. A small external script polls instance identity and
returns the browser to the fresh workspace without opening a duplicate browser tab. Native
form submission offers a manual return link when JavaScript is unavailable. Servers launched
outside the managed launcher explain that Start VOP is needed for restart controls.

Validation commands/results on Windows:

- `.\.venv\Scripts\python.exe -m pytest -q`: 291 passed, 4 skipped in 45.44 s.
  The skips are Linux-only helper tests.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_lifecycle.py tests/test_phase4_worker.py`:
  36 passed in 8.47 s after final cleanup/UI spacing changes.
- `.\.venv\Scripts\python.exe tools\restart_smoke.py`: PASS twice. Disposable loopback
  mock workspace passed browser-endpoint full interpreter restart and launcher replacement;
  access key and 3 recorded observations retained. No camera or model weights used.
- `.\.venv\Scripts\python.exe tools\phase4_smoke.py`: PASS; explicit mock worker over
  actual loopback HTTP, 3 observations persisted after restart, browser health form and
  disposable real Windows DPAPI check passed. No cameras connected or weights loaded.
- `.\.venv\Scripts\python.exe tools\build_release.py`: PASS;
  `dist/vop-0.5.0-windows-dev.zip`, SHA-256
  `e1ebc3ffe2bf73d93f56c4bc1f278efb50620b8a6999c99fc886bf60ed4315a5`.
- `git diff --check`: passed.

Regression checks cover authorization, CSRF, unavailable managed controls, fresh instance
identity, shutdown during an admitted capture, stopping new sampling, process identity,
unrelated-port protection and launcher-ancestor exclusion. The restart smoke is also added
to both existing CI platforms; CI results are not claimed here.

The actual laptop app was idle with no scheduled sources when the updated launcher was
applied using:

`.\.venv\Scripts\python.exe tools\run_dashboard.py --allow-live-sources --remember-access-key --open-browser --restart-existing`

Authenticated JSON health checks returned HTTP 200 after replacement. All 889 observations
and saved enabled/evidence/interval controls were retained. No camera, inference or GPU test
was requested for this UI/lifecycle change. No model revisions, dependencies or schema changed;
the historical approved d1 revision remains
`051bcc464b01b9f92942b364d9586b0ef5912432`.

Limitations: a responsive managed server gets up to 90 seconds to stop before stale cleanup;
unresponsive or legacy instances cannot guarantee that an in-flight sample finishes. Closing
owned SSH processes lets the existing bounded remote-session cleanup restore its prior
workload, but this change does not newly validate that remote hardware path. GUI recovery
times out with a Start VOP remediation if startup fails. Browser reconnect logic was tested
through endpoint/real-process checks, not a new visual browser automation run.

Recommendation: use Start VOP for a clean launch and the web Restart VOP control for normal
maintenance in the existing Phase 4 pilot. Phase 5 remains unauthorised.

## Corrections after initial PR #19 checks

The original Ubuntu CI run passed unit tests and Phase 1–4 smoke checks but failed the new
restart smoke: its replacement launcher waited for an exited Linux zombie that only the
smoke parent could reap. Treat zombies as exited when waiting for graceful shutdown.
The matrix cancelled Windows after that Ubuntu failure. The initial PR is not ready to merge
until the corrected Windows and Ubuntu jobs complete.

A direct Windows launch also exposed AppData virtualization: the normal and packaged-Codex
launches could use different encrypted files despite the same account and apparent AppData
path. The camera records survived, but the direct launch could not find their matching files.
Use `%USERPROFILE%/.vop/secrets` outside redirected AppData. On first read of a missing value,
validate and copy the newest legacy encrypted file from AppData or Codex LocalCache. Keep
originals and use an atomic no-replace publish, so migration cannot overwrite a concurrent
new save. An explicit `VOP_SECRET_DIR` isolates smoke tests and disables migration there.
Partial camera edits preserve readable fields and use an address placeholder without a
misleading example IP. Missing-value guidance links to setup rather than repeating restart.

Additional changed files: `src/vop/secrets.py`, `src/vop/ui_readiness.py`,
`src/vop/integration_ui.py`, `tests/test_secret_migration.py`,
`tests/test_protected_settings.py`, `tools/phase4_smoke.py` and the existing restart files.

Correction validation on Windows:

- `.\.venv\Scripts\python.exe -m pytest -q`: 298 passed, 4 skipped in 54.80 s.
- Focused migration/lifecycle/camera checks: 46 passed in 11.64 s before the additional
  shared-root invariance regression was included in the full suite.
- `.\.venv\Scripts\python.exe tools\restart_smoke.py`: PASS; 3 observations and key retained.
- `.\.venv\Scripts\python.exe tools\phase4_smoke.py`: PASS with isolated disposable vault;
  mock worker, no cameras or model weights.
- `git diff --check`: passed.

Recovered all three actual saved camera profiles to the shared encrypted vault. The saved
addresses matched their existing allowed-address policies; no camera addresses or passwords
were changed and original encrypted files remain. The app was restarted with the corrected
launcher. Authenticated health and camera-setup readiness were checked without camera capture
or model inference. Camera setup readiness proves protected values can be read, not that a
camera is reachable. This corrects the initial same-context-only restart validation gap.
CI for the correction will be checked on both platforms before recommending merge. The earlier
release archive/hash above is historical and predates this correction.
