# Phase 5 — Capture recovery and Diagnostics

Date: 28 October 2026, Europe/London. VOP 0.6.2. Scope: restore stopped observations,
add Diagnostics, and the owner's follow-up requests for noticeable traffic lights.

## Actual diagnosis and recovery

Protected-bearer JSON checks showed three cameras enabled with monitoring intervals,
but the sampler reported `worker_reconnect_failed`. No new observations could get past
engine preparation. Python name resolution and strict, noninteractive SSH showed:

- `antec.local` did not resolve on this laptop.
- `antec` resolved and connected successfully using `HostKeyAlias=antec.local` and
  `StrictHostKeyChecking=yes`. The same check succeeded with the exact SSH executable
  selected by the app. No key checking was disabled or new host identity accepted.

The failure occurred before camera capture. Camera settings did not need changing.
After the fix, passive diagnostics showed the existing monitoring schedule producing
**successful results for all three cameras**, with the engine ready, no engine error,
the managed session active and connection name `antec`. No manual camera test, image
inspection or new benchmark was used to obtain that evidence.

## Changed files

| Files | Change |
|---|---|
| `src/vop/worker_session.py` | Canonical name first; short-name fallback only on name-resolution failure, always using the original trusted SSH identity |
| `src/vop/operator_workflow.py` | Same target selection for protected key recovery, clear old recovery errors after success, simple remediation messages |
| `src/vop/pipeline.py`, `storage.py` | Active observation stage/time; mark engine-preparation failures as waiting for engine rather than camera disconnection; retain UNKNOWN answers |
| `src/vop/sampling.py` | Per-camera error/backoff bookkeeping, including exceptions during engine preparation; retries are bounded and use completion time in live sampling |
| `src/vop/diagnostics.py` | Passive redacted HTML/JSON snapshot, prominent traffic lights, explicit reconnect and existing queued camera-only tests |
| `src/vop/dashboard.py`, `browser_auth.py`, `service.py` | Navigation in both modes, Observe error guidance, traffic-light CSS/tooltips, authenticated/CSRF-protected operations and installation |
| `src/vop/integration_ui.py` | Timestamp future camera-only connection tests, preserving legacy timestamps when available |
| `tests/test_diagnostics.py` | Offline name/trust, passive reads, permissions, stage/serialization, failure/UNKNOWN/backoff, recovered state and traffic-light checks |
| `tests/test_operator_workflow.py`, `test_worker_session.py`, `test_ui_modes.py` | Offline resolver fixtures and updated navigation expectations |
| `README.md`, `CHANGELOG.md`, `pyproject.toml` | Runbook, release notes and version 0.6.2 |

## Diagnostics behaviour

- Opening Diagnostics does not perform DNS, SSH, worker health RPCs, model starts,
  camera probes or image retrieval. It reads local state, protected setup availability
  and indexed latest-result metadata. Private endpoints, credentials, raw provider data
  and imagery are not returned. Viewer access is read-only.
- A large summary and component/camera indicators each have a high-contrast three-lamp
  panel. Lamps are 22 px; the summary uses 28 px lamps and larger text. Only one lamp is
  lit. Accessible/visible labels convey meaning without relying on colour.
- Green means recent successful acquisition/check or a running service. Amber means
  paused, waiting, stale or unverified. Red means a reported failure or an unexpectedly
  stopped scheduler. These lights do not measure model accuracy or certify connectivity.
- Camera freshness is bounded by max(00:01:00, three target intervals); cached engine
  readiness older than 00:01:00 becomes amber. Paused/disabled/unconfigured monitoring
  stays amber rather than being labelled a camera failure. Old outcomes are timestamped.
- The page shows scheduler state, the active observation stage and total elapsed time,
  selected engine/recovery/session state, named cameras, target intervals, enabled question
  counts, last observation image/attempt, last camera-only test, queue intent and backoff.
- Check and reconnect engine is an explicit operator POST. It waits for the observation
  slot off the event loop and reuses the existing bounded recovery/session policy. It
  does not request camera frames. Existing enabled monitoring resumes automatically.
- Camera-only tests use the existing queued connection-test route, now available to
  operators from View-mode Diagnostics. They request no inference. Configuration edits
  still require Configure mode. Refresh diagnostics reads a newer snapshot; no automatic
  polling or page reload was added.

## Commands and observed results

Windows repository Python 3.11 environment:

- `.\.venv\Scripts\python.exe -m pytest -q` — **446 passed, 4 skipped in 222.78s** at
  the main recovery/diagnostics snapshot, before the final status/traffic-light refinements.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_diagnostics.py tests/test_operator_workflow.py tests/test_worker_session.py tests/test_ui_modes.py tests/test_phase2_sampling_roi.py`
  — **46 passed, 4 skipped in 25.72s**, including final traffic-light state checks.
- `.\.venv\Scripts\python.exe -m pytest -q tests/test_diagnostics.py tests/test_metric_help_camera_names.py tests/test_ui_modes.py`
  — **15 passed in 12.48s** before the additional traffic-light regression case.
- `.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .`
  — VOP 0.6.2 installed. No new dependency or schema migration.
- `.\.venv\Scripts\python.exe -m pip check` — no broken requirements.
- `.\.venv\Scripts\python.exe tools/restart_smoke.py` — PASS: fresh interpreter,
  stale-instance replacement, retained key and three synthetic observations; no real camera/model.
- `.\.venv\Scripts\python.exe tools/build_release.py` — PASS: 0.6.2 wheel/portable ZIP.
- `git diff --check` — passed; normal Windows line-ending notices only.

The four default Windows skips are the Linux-only offline remote-session helper cases;
real model/camera acceptance is separate from the default suite. Tests substitute DNS,
SSH processes, capture and inference. No network device or secret is needed by those tests.
Final full Windows/Ubuntu push/PR checks are recorded on the pull request after push and
are not presumed by this local report.

## Activation and limits

Managed activation returned HTTP **202**, a fresh ready instance and unchanged control
tuples `(enabled, retain_evidence, sample_interval_seconds)` for all **three** cameras.
The first activation's observation count was **29571 → 29573**; later passive checks
confirmed successful normal monitoring for all three. A subsequent managed activation
also preserved controls (**29814 → 29816**). Normal monitoring can start the existing
owner-authorised timed GPU session; it is not a new benchmark or changed priority policy.

No camera credentials, saved endpoints or host-key files were edited. No manual Tapo,
audio, email/SMS, real camera or GPU benchmark test was run. The existing pinned d1-3B
revision remains `051bcc464b01b9f92942b364d9586b0ef5912432`; no new performance measurements
are claimed. No live page/image inspection or browser visual QA was performed; prior
restricted browser access was not retried. Traffic-light markup, CSS and state behaviour
were checked offline; the owner can review the live presentation.

Both host names can still be unavailable if Antec is asleep or disconnected. Unknown or
changed SSH keys still stop recovery. Diagnostics is a timestamped snapshot, not a live
network guarantee; refresh or use the explicit checks for newer evidence. Existing full
history replay during saving can limit observation frequency; stage/time reporting now
makes that wait visible, but this change does not replace temporal replay semantics.

Recommendation: remain in Phase 5. Review the prominent lights, verify continued monitoring
and use the explicit checks for future failures. No Phase 6 work or automatic merge.
