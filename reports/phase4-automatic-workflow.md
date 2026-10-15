# Phase 4 automatic operator workflow — 15 October 2026

The owner requested a clearer, substantially automated UI and explicitly chose temporary VOP
GPU priority, with the other Antec workload restored after a timed session. This update remains
within the existing foreground Phase 4 pilot. It adds no OS autostart, permanent service, new
model, fallback model, driver change or Phase 5 deployment.

## Normal workflow

Open Start VOP → signed-in workspace → Observe now or Start monitoring. Saved backend, cameras
and questions are reused. New cameras can be saved, enabled and preview-checked in one action;
IDs are generated when omitted. A one-time Use Antec AI preset replaces manual worker-profile
entry. Advanced settings retain manual selection, keys, session controls and question/timing
parameters. Explicitly paused sources stay paused; Enable and observe makes a single observation
without resuming a saved schedule. Monitoring defaults to 10 seconds or reuses the saved custom
interval, and pause state survives restart. Pausing the last scheduled source stops the owned
session when no inference is in flight; otherwise its existing lease bounds it.

Antec readiness and key recovery happen before image acquisition. The controller reuses a ready
worker or an owned session, recovers the existing worker token over verified trusted SSH, and
starts at most one 15-minute owned session while connecting. It waits up to 30 seconds for
health, uses a short retry cooldown, records genuine connection failures as Unknown gaps, and
never fabricates answers or changes worker identity/model. Fatal failure of a newly owned
session requests cleanup/restoration. Existing remote cleanup on Stop/EOF/lease remains in use.
Configured sampling may request another timed session when inference is next due. Other backend
profiles are health-checked but never automatically reprovisioned or replaced.

Long-lived keys stay internal. The launcher verifies that a same-account VOP launcher from this
installation owns its loopback listener before sending authentication. An authenticated local
API mints a one-use, 60-second browser ticket; the operator key is not put in the URL. Minting is
available during capture; viewer keys/cookie-only clients cannot mint. Tickets are bounded in
memory, consumed once, and not stored. Manual sign-in and explicit --show-access-key remain
advanced. Unreadable saved login keys are never silently rotated; unrelated port listeners are
never taken over. This reduces the earlier reboot confusion without claiming that the original
process/DPAPI discrepancy has been fully diagnosed.

## Changed files

- src/vop/operator_workflow.py: local launch tickets, bounded on-demand Antec orchestration,
  existing-key recovery and plain-language remediation messages.
- tools/run_dashboard.py: automatic signed-in browser opening, listener verification, startup
  retry, internal keys and manual-worker/show-key advanced switches.
- src/vop/browser_auth.py and service.py: ticket authorization and opt-in automation plumbing;
  ordinary service/API construction keeps automatic recovery disabled by default.
- src/vop/pipeline.py: dependency recovery before acquisition and truthful Unknown failure gaps.
- src/vop/dashboard.py and integration_ui.py: normal Observe/monitor actions, progress feedback,
  generated IDs, combined camera setup/check, collapsed advanced forms and remediation buttons.
- src/vop/ui_readiness.py: repairable worker problems no longer block automatic recovery.
- tests/test_operator_workflow.py and test_phase2_controls.py: regression coverage.
- README.md, CHANGELOG.md, CODEX_PHASE_4_PLAN.md and this report: workflow, owner authorization,
  operating limits and evidence. No dependency or schema migration was added.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests/test_operator_workflow.py -q
.\.venv\Scripts\python.exe tools\phase4_smoke.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tools\build_release.py
```

The actual-loopback Phase 4 smoke passed, including restart/disconnection and real Windows DPAPI;
pip check reported no broken requirements. Offline workflow tests use fake SSH/services and
synthetic frames, with no external network/model/camera. They cover ticket authentication,
expiry/replay, listener refusal, session reuse/key repair, failure/cleanup, UI remediation,
combined camera setup, generated IDs and monitoring persistence/custom intervals. A Node VM
fixture verified Working feedback preserves the submit action/value; it is not a browser pass.

After refreshing the idle owned dashboard, authenticated loopback health returned HTTP 200,
ready, with automatic recovery enabled. The real launcher listener check and ticket exchange
returned 303 on redemption, 200 for cookie-authenticated JSON health, and 401 on replay. This
metadata-only check did not inspect user pages or acquire camera images or load the model.

## Limits and next validation

No new camera/GPU inference or model measurement is claimed. Historical d1 revision remains
051bcc464b01b9f92942b364d9586b0ef5912432. The established Antec installation, model cache and
trusted noninteractive SSH login must already exist; VOP does not accept unknown SSH host keys
or install dependencies/drivers/models automatically. First-time camera addresses/accounts and
question wording still need user input. Connection recovery waits are bounded and offer retry
if a worker is slow or a machine is asleep. Login recovery after a genuinely unreadable Windows
vault requires the same OS account; no new key is silently created over an existing file.

A physical overnight reboot and new real-GPU/real-camera acceptance run were not performed.
The prior process rejecting the saved dashboard key despite readable files remains unexplained;
restart recovered access and the new workflow avoids manual key handling and reports failures
without asking for a worker key. Local-page browser automation remains restricted, so no new
real-browser visual pass is claimed. Continue supervised Phase 4 acceptance through Start VOP,
one-shot observation, monitoring/pause, then reboot/reopen. Phase 5 remains unauthorised.


Final Windows full suite: **251 passed, 4 skipped** (Linux-only helper cases). The release
builder passed; ZIP SHA-256:
`2caf91f63228834f54d1d8edc0865c43660fe97b8e54569d077d9af53867793b`.
The earlier focused workflow/control/browser checks passed, and all final workflow regressions
are included in the full-suite result. No new dependencies or model versions were installed.
