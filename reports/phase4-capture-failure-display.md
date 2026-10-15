# Phase 4 capture failure display — 15 October 2026

The owner reported Internal Server Error after observing C200. The server traceback showed
dashboard.capture dividing elapsed_ms=None by 1000. The latest three stored runs independently
showed capture_timeout with null timing. Acquisition failed before inference, so null timing
was correct; the result renderer incorrectly assumed every run had numeric inference timing.

## Changes

- src/vop/dashboard.py: show that inference did not run when timing is null, without inventing
  zero seconds. Keep numeric timing for actual inference attempts. Use existing recovery text
  when a failure has no dedicated guidance. Camera failure links remain in the camera workspace.
- tests/test_phase4_worker.py: parameterised acquisition timeout and open-failure regressions
  exercise the actual pipeline and browser POST route, returning HTTP 200, clear failure text,
  retry controls and null timing. Inference must not be called. Persisted normalised errors
  retain null answers and the temporal summary remains UNKNOWN.
- README.md and CHANGELOG.md: explain failure behavior and the camera connection check.

## Actual commands and results

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 263 passed, 4 skipped in 35.20s (four Linux-only helper cases)
.\.venv\Scripts\python.exe tools\phase4_smoke.py
# PASS: synthetic loopback HTTP, worker disconnect/restart, real Windows DPAPI
git diff --check
```

VOP's owned Antec session was stopped through the authenticated existing stop endpoint before
reloading the idle app. The normal cleanup completed; a read-only trusted SSH check of
systemctl --user is-active llama-mtp.service returned active. Saved-key JSON health returned
HTTP 200 after reload, with automatic recovery enabled and C200 protected setup readable.
No camera image, secret value or protected user-page HTML was read for this diagnosis.

## Remaining validation

This fixes the UI crash, not the underlying camera timeout. No new real-camera capture or
model/GPU inference was requested during the repair. No new benchmark or model version is
claimed; historical d1 revision remains 051bcc464b01b9f92942b364d9586b0ef5912432. The UI regressions
use offline failure fixtures, and no new browser visual pass is claimed. The earlier reboot
protected-store discrepancy remains separate and unresolved.

Continue Phase 4: open C200 and select Test camera to check its connection, then retry Observe.
Phase 5 remains unauthorised. No auto-merge is requested.
