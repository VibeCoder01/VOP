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

Windows: **211 passed, 4 skipped** (the Linux-only Bash lifecycle cases). Phase 4 HTTP smoke
passed with restart persistence, disconnect-to-UNKNOWN and real Windows DPAPI. `pip check`
reported no broken requirements. The release builder passed and includes the launcher.
Both jobs passed in [the observed Windows/Ubuntu CI run](https://github.com/VibeCoder01/VOP/actions/runs/38635304638)
for implementation commit `6e177c0`, including the Linux-only lock/lifecycle checks. The rebuilt
wheel was reinstalled into the separate temporary Windows installation and its bundled Phase 4
smoke passed. Archive SHA-256: `15d2e05dcf64ee6902ea1d63caac37c6169d3aeb13d5656753adad57aaf01b35`.
Read-only `bash -n` validation on antec passed for the helper, and `command -v` confirmed Bash,
setsid, flock, ss and systemctl exist. SSH login with BatchMode and strict host verification also
passed using the running dashboard's environment. These checks did not pause services or run
inference. The refreshed dashboard reused the actual protected operator key across processes;
no new laptop reboot or real-browser opening test was performed for the launcher.
Tests use synthetic frames, fake SSH
processes and fake services, not real cameras or model weights. The Linux-only remote helper
test executes the actual Bash script against temporary offline commands for Stop, stdin EOF, timeout
and refusal of an already-owned remote session lock;
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


## Recoverable source and question removal — 14 October 2026

The owner requested removable Sources and Questions. Both listings now offer Remove… with a
confirmation page, plus Removed sources/questions → Restore. Configuration removal persists in
existing schema-3 release settings; immutable question versions, observations, events, evidence
and protected camera values are retained. Sources leave the active pipeline; questions leave
its current question list. Removed IDs must be restored before reuse. Restore leaves monitoring
disabled, and source restore clears sampling and evidence retention. Dependent rules receive a
new disabled revision; pending/retrying webhook deliveries are cancelled without rewriting the
original alert payload or delivery attempt counts. Existing delivered notifications cannot be recalled.

Changes: `src/vop/removal.py` implements the forms and coordinated capture/rule locking;
`storage.py`, `pipeline.py`, `integration_ui.py`, `sampling.py`, `reliable.py`, `service.py` and
`dashboard.py` preserve removal across startup and omit removed items from capture/current
configuration. `config.py` supports empty source/question lists. Full database backups retain
recovery records, including sources omitted from the exported current configuration. README
and CHANGELOG explain removal, restoration and retained data. No schema migration or dependency
was added. Offline regression coverage is in `tests/test_removal.py`.

Validation commands are the same full pytest, Phase 4 smoke and pip-check commands shown above;
removal-specific command: `.\.venv\Scripts\python.exe -m pytest tests/test_removal.py -q`
(**6 passed**). Checks cover confirmation-only GET, CSRF/viewer denial, occupied capture slots,
immutable history, alert cancellation, protected camera setup, restart, empty configuration and
actual backup/restore recovery. The Phase 4 HTTP smoke passed; pip check found no broken
requirements. Final Windows full suite: **217 passed, 4 skipped** (Linux-only helper cases).

No real camera, GPU/model inference or service interruption test was run for removal. The pinned
model revision and historical measurements above remain unchanged. Removal is recoverable,
not permanent data erasure; protected credentials and retained evidence require their existing
separate management/deletion workflows. Continue supervised Phase 4 testing; Phase 5 remains
unauthorised.

The release builder (`.\.venv\Scripts\python.exe tools\build_release.py`) passed. Updated archive
SHA-256: `4b2774a16cdcab969c160288bed3faeb97a14940a0d8cf9c0f91f35f21bbf716`.
The idle owned dashboard was restarted with the same DPAPI-protected key and live-source opt-in;
authenticated `/api/v1/health` returned ready with no sampling/rule errors. No user configuration
was removed during validation. Actual local browser automation remains blocked as noted above.
