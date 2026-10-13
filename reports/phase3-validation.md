# Phase 3 validation — 13 October 2026

Recommendation: **CONDITIONAL GO for review and laptop development testing**. The owner
accepted Phase 2 and authorised the next phase. The Phase 3 reliable-release capabilities
are implemented; this is not a claim that all hardware/production MVP gates are complete.
Phase 4 has not started. PR must be reviewed/merged by the owner, never automatically.

## Changed files and traceability

- `src/vop/reliable.py`: schema-v3 rules/revisions/transitions/alerts/delivery, exports, retention,
  configuration snapshot, consistent backup and validated new-directory restoration.
- `src/vop/release_ui.py`: native operator forms, alert filters/notes, CSV/JSON/config downloads,
  retention preview/apply, audit listing and read-only alert API.
- `src/vop/storage.py`, `service.py`, `dashboard.py`, `browser_auth.py`: migration backup,
  independent rule worker, shared native layout/control IDs and bounded login attempts.
- `tools/release.py`, `build_release.py`, `phase3_smoke.py`, `dependency_audit.py`:
  offline maintenance, allow-listed ZIP/wheel, real HTTP/recovery smoke and explicit online scan.
- `install/windows.ps1`, `install/README.md`: checksum validation, fresh venv/locked dependency
  installer, smoke and rollback instructions; no OS service or global Python modifications.
- `tests/test_phase3_release.py`: new meaningful transition/security/recovery checks;
  existing schema expectations updated in Phase 1/2 storage tests.
- `requirements-offline.txt`, `pyproject.toml`: package 0.4.0 and verified security updates.
- `AGENTS.md`, `CODEX_PHASE_3.md`, `README.md`, `CHANGELOG.md`, `.gitignore`, CI workflow:
  authorisation, phase gates, operating limits, artifact exclusions and release build jobs.

| Gate | Evidence/result |
|---|---|
| P3-01 | Duration/count/current-version rules; separate health rules; immutable revision table and criteria in alert payload. Passed offline checks. |
| P3-02 | One-hour sampled fixture produces one alert; repeated evaluation/restart retains stable ID; UNKNOWN suspends and resume does not duplicate duration alert; acknowledge/resolve/notes audited. Passed. |
| P3-03 | Five simulated temporary failures end in visible failed state; interrupted sending recovers with same key; simulated HTTP 503 carries key/token; unapproved/plaintext/credential/fragment URLs denied without connection. Passed. No real webhook sent. |
| P3-04 | Actual HTTP CSV/JSON downloads and viewer permission checks; timezone/provenance, version and formula protection. Passed. |
| P3-05 | Configuration round-trip preserves policy/disabled control/mock preset/rules; bad path/schema rejected before destination publication; backup restores 18 observations and acknowledged alert; corrupt checksum rejected; v2 backup remains v2. Passed. |
| P3-06 | Preview leaves pixels intact; explicit application deletes old synthetic evidence and raw detail; normalized replay reproduces events; independent windows validated; hourly enforcement is enabled only after apply. Passed. |
| P3-07 | Wheel/ZIP built; fresh Windows venv install with pinned dependencies, pip check and actual Phase 3 smoke passed. Development installer, not standalone executable/service. |
| P3-08 | 180 offline tests passed; previous Host/origin/CSRF/viewer tests retained; new rule validation, formula/XSS/endpoint/rate-limit/native-form checks pass. Browser and CI evidence recorded below. |

## Exact commands and local results

Executed in PowerShell from `C:\Users\shaun\Documents\ChatGPT\VOP`, Python 3.11.9:

```powershell
.\.venv\Scripts\python.exe -m pip install Pillow==12.3.0 setuptools==83.0.0 pytest==9.0.3 Pygments==2.20.0
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m vop demo --image fixtures/scene.png --engine mock
.\.venv\Scripts\python.exe tools\phase1_smoke.py
.\.venv\Scripts\python.exe tools\phase2_smoke.py
.\.venv\Scripts\python.exe tools\phase3_smoke.py
.\.venv\Scripts\python.exe tools\build_release.py
.\.venv\Scripts\python.exe tools\dependency_audit.py --allow-network
```

- `pip check`: no broken requirements; app 0.4.0 installed.
- pytest: **180 passed**. The initial run exposed hardcoded schema-v2 expectations, which were
  updated to v3/v4 future-version refusal. New tests and actual browser work caught mistakes
  during implementation; only corrected reruns are acceptance evidence.
- mock CLI demo: success, explicit synthetic fields, no weights.
- Phase 1 actual subprocess smoke: PASS, 201 capture, 401 unauthenticated, 200 duplicate,
  six observations after restart, loopback only.
- Phase 2 actual subprocess smoke: PASS, login/CSRF/replay, 403 viewer evidence,
  deleted evidence 404, six views, 21 observations after restart.
- Phase 3 actual subprocess smoke: PASS, one count-rule transition, durable acknowledgement,
  CSV/JSON, 403 viewer configuration denial, retention preview, backup/restore preserving
  **18 observations and the same acknowledged alert**. No cameras/outbound channel configured.
- ZIP built at ignored `dist/vop-0.4.0-windows-dev.zip`, containing
  `vop-0.4.0-py3-none-any.whl`, synthetic fixture, pinned requirements and allow-listed tools/docs.
- Fresh extracted ZIP installed with a new temporary venv using
  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File <fresh-dir>\install\windows.ps1 -Python C:\Users\shaun\AppData\Local\Programs\Python\Python311\python.exe`.
  This process-only policy override did not change the system execution policy. The installer
  passed hashes, dependency installation, pip check and the real Phase 3 smoke. Temporary
  installation directories are isolated from the user's current app/database.

## Dependency check

The opt-in scan queries the [OSV batch API](https://google.github.io/osv.dev/api/) with public
offline package names/versions only. It is excluded from default offline tests/CI. Initial findings
affected setuptools 80.9.0, Pillow 12.0.0, pytest 8.4.2 and Pygments 2.19.2. OSV advisory fixed
ranges prompted installed/pinned replacements 83.0.0, 12.3.0, 9.0.3 and 2.20.0 respectively.
Repeat scan at **2026-10-13 21:21:42 UTC**: **35 packages checked; no known findings returned**.
This is time-specific dependency evidence, not a guarantee against unknown vulnerabilities.
Historical Phase 0 Linux/model closure is unchanged and was not scanned as a current release.

## Browser and CI

Playwright uses a dedicated disposable browser `vop-phase3` and synthetic server on loopback
port 8877; it never modifies the user's running port-8765 database. Native form encoding and
unique IDs are regression-tested after browser work caught the common Form helper's multipart
default, incompatible with the application's deliberately URL-encoded CSRF middleware.
Native browser creation of a count rule, synthetic demo, one MOCK alert and acknowledgement/note
submission passed. At 390×844, document width fits the viewport after fixing grid min-width and
filter wrapping; desktop/mobile screenshots were inspected in ignored `output/playwright/`.
An initial Windows CI run found temporary-path alias normalization in configuration import;
the staging directory/expected path now resolve consistently, with an aliased-temp-path regression.
Final CI results will be appended after completion, not predicted.

## Hardware, model and delivery limitations

- **No new camera, RTSP, model download, GPU or antec run in Phase 3.** The expressly authorised
  Phase 2 USB capture result and Phase 0 pinned d1-3B CPU benchmark are historical evidence only.
  Actual RTSP AT-02 and real camera/model workload accuracy acceptance remain pending; no
  supplied camera endpoint or labelled workload was available. AT-01 software/capture passes
  do not establish real model vision accuracy. No new revision/latency/RAM measurement exists.
- AT-03–10 regressions pass on fixtures; AT-11 software alerts/retry/ack/restart pass;
  AT-12 regression hardening passes. Do not call this “all MVP hardware ATs passed”.
- No real outbound delivery test: sink behaviour/HTTP policy are simulated in offline tests;
  dashboard delivery runs in actual HTTP smoke. HTTPS webhook requires explicit environment
  URL/host policy and per-rule opt-in; email is not implemented. A receiver must deduplicate keys
  after ambiguous connection/crash. Five attempts cap retries, not exactly-once reception.
- Normalized history, event/query revisions and frame metadata remain after raw/evidence retention;
  no full history erasure, backup auto-pruning or storage quota. Offline restore/import deliberately
  create a new directory; the operator must protect/remove old backup files separately.
- Single process/one alert worker; full replay is O(n), intended for development datasets. Heavy
  injected inference has the existing soft deadline; no production remote worker or hard-kill model
  isolation is introduced. Foreground install uses loopback auth, not Windows service deployment.
- Application licensing, OS-bound persistent secret provisioning, production access policy and
  workload calibration remain deployment decisions. No independent penetration-test or certified
  safety/medical alert claim is made. Advisory duration uses bounded sample intervals.

Next recommendation: review/test this Phase 3 development release, then close the reference
camera/model accuracy and deployment gates before calling it production-ready. Expanded inputs
or remote inference need a separately scoped authorisation; Phase 4 has not started.
