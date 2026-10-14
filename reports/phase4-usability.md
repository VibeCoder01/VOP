# Phase 4 practical-use follow-up — 14 October 2026

Owner requested practical startup/connection and camera/result usability improvements. Scope
remains Phase 4; Phase 5 and unattended deployment remain unauthorised.

## Changes

- `Start VOP.cmd`, `tools/run_dashboard.py`: manual double-click startup, browser opening,
  reuse of an existing local listener, and explicit Windows DPAPI storage/reuse of the operator
  access key. An unreadable stored key is not silently overwritten.
- `src/vop/worker_session.py`, `service.py`, `integration_ui.py`: owner-only 15/30/60-minute
  sessions for the established antec installation. Explicit checkbox permission is required
  before pausing its existing llama service. The SSH tunnel binds only loopback, verifies the
  existing host key and uses noninteractive authentication. Existing tunnels are not taken over.
  The remote Bash helper uses a timed stdin lease and EXIT/HUP/TERM cleanup, stops its owned
  worker process group and restores only the previously active service. App shutdown requests
  graceful cleanup; no persistent service, auto-launch, model download or live capture is enabled
  by installing this code.
- `dashboard.py`, `integration_ui.py`: readable health/capture answers, clear missing-consent
  guidance, separate image permission control, Capture again, expandable technical details.
- Regression tests, release allow-list, README and changelog cover these changes.

## Validation and limits

Exact local commands:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\phase4_smoke.py
.\.venv\Scripts\python.exe -m pip check
```

Windows: **211 passed, 3 skipped** (the Linux-only Bash lifecycle cases). Phase 4 HTTP smoke
passed with restart persistence, disconnect-to-UNKNOWN and real Windows DPAPI. `pip check`
reported no broken requirements. The release builder passed and includes the launcher.
Tests use synthetic frames, fake SSH
processes and fake services, not real cameras or model weights. The Linux-only remote helper
test executes the actual Bash script against temporary offline commands for Stop, stdin EOF and timeout;
it is skipped on Windows. Real use of the newly added dashboard session controls still requires
the owner's explicit Start action and pause permission. No new GPU benchmark, labelled dataset
or camera-accuracy result is claimed for this software change. Browser automation of the local
user page was previously blocked by its security policy; the new pages are verified through
authenticated offline HTTP tests rather than claimed as a new real-browser pass.

Historical owner-provided live evidence from this day does establish C200 → laptop → SSH →
real antec CUDA/BF16 d1-3B → stored response. At 20:30:51 UTC, the model returned human_present
true (2.016 seconds inference); a ground-truth positive label was not explicitly supplied. At
20:33:09 UTC it returned false (267.421 ms inference), and the owner explicitly stated nobody
was present. These are individual pilot examples, not an accuracy estimate. Official model
revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`; no model/version change was made.
The prior 15-minute manual test wrapper subsequently reported its original service restored.

Open limits: the earlier reboot-time secret-access failure remains unexplained; retained files
were readable in main/thread/spawn probes and capture resumed after a dashboard restart.
C210/C510W, challenging labelled scenes, reduced-precision task accuracy and a live/GPU soak
remain pending. Recommendation: continue supervised Phase 4 pilot use and validate the new
manual session controls; do not infer Phase 5 or permanent GPU scheduling approval.
