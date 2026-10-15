# Phase 4 protected-settings incident — 15 October 2026

After a physical PC restart, the owner reported that C200's protected details were unavailable.
All four existing DPAPI values remained readable in a fresh process, including 200 concurrent
reads. The running launcher used the same Windows account, installation and LOCALAPPDATA,
with no inherited VOP_API_TOKEN override, but rejected the persisted dashboard key (HTTP 401).
Fresh-process camera endpoint policy and credentials validation passed. File timestamps did
not indicate credential replacement during this diagnosis. The original process discrepancy
has not been explained and is not claimed fixed.

Only the idle owned VOP process was restarted; no camera/GPU operation or SSH session was
active. Browser processes were retained. No credentials were replaced or exposed. After restart,
saved-key health returned HTTP 200 and the running app's camera_setup reported tapo-c200 ready.
This validates protected setup readability, not camera reachability or model inference.

## Changes

- src/vop/secrets.py: bind DPAPI functions and their Blob structure once, removing per-call
  mutation of shared ctypes signatures; type LocalFree explicitly. Log only error category and
  Windows error number on failure, without values, references or private paths. The signature
  race was found by inspection; it is not proven to explain this incident.
- src/vop/ui_readiness.py: separate endpoint-policy errors from protected-store failures and
  clarify that saved details have not been deleted.
- src/vop/service.py: authenticated health includes network-free camera_setup readiness booleans.
- tests/test_protected_settings.py and tests/test_phase1_service.py: disposable cross-process
  concurrent DPAPI reads, safe diagnostics, distinct errors and secret-free health regression.
- tests/test_removal.py: disable the background sampler in the persisted-controls removal test;
  Windows CI exposed a pre-existing race with its immediate scheduled capture (HTTP 429).
- README.md and CHANGELOG.md: recovery instructions and candid unresolved limitation.

## Actual verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 255 passed, 4 skipped in 34.59s (before adding the final health-route regression)
.\.venv\Scripts\python.exe -m pytest tests/test_phase1_service.py tests/test_protected_settings.py -q
# 29 passed in 3.29s, including that final regression
.\.venv\Scripts\python.exe -m pytest tests/test_removal.py tests/test_phase1_service.py tests/test_protected_settings.py -q
# 35 passed in 13.04s after isolating the removal test's background sampler
.\.venv\Scripts\python.exe tools\phase4_smoke.py
# PASS: synthetic loopback HTTP, persisted restart, disconnect Unknown, real Windows DPAPI
git diff --check
```

Four full-suite skips were Linux-only helper cases. Cross-process DPAPI tests use only disposable
generated values; offline tests deny network. No new camera capture, GPU/model run, weights,
revision or dependency change occurred. Historical d1 revision remains
051bcc464b01b9f92942b364d9586b0ef5912432. No new browser visual pass is claimed.

Continue Phase 4: refresh the workspace and try the normal observation action. On another reboot,
retain the VOP terminal error category/Windows code if the warning recurs; do not replace saved
credentials merely because they appear unavailable. Physical reboot reliability remains open.
Phase 5 remains unauthorised.
