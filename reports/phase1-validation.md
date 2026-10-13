# Phase 1 validation — 13 October 2026

Authorised by the owner after Phase 0 PR #1 merge. Branch `codex/phase-1`, based on
merged `main` commit `2a4097c`. Scope: SRS §15 Phase 1 and `CODEX_PHASE_1.md`.
No SRS requirements were renumbered or redesigned. Phase 2+ remains unauthorised.

## Implemented foundation

- Versioned operator-owned JSON config, independent source and engine identities, explicit
  secret environment references for network camera endpoints, and synthetic sample config.
- Synthetic/file acquisition and optional one-shot USB/RTSP/HTTP snapshot adapters; shared
  JPEG/PNG byte validation, 20 MiB limit, exact host policy, disabled redirects/proxies,
  explicit live-source consent and killable capture child.
- Transactional SQLite schema v1, immutable question versions, frames (metadata only),
  run/native results, per-question observations and minimal audit. Configuration restart
  is idempotent; changed question content must increment the version. Unknown/newer DBs fail closed.
- Loopback FastHTML/Starlette HTTP service with mandatory single-operator bearer authentication
  on every route. No default secret, cookies, public health exceptions or URL-token authentication.
- Authenticated capture, byte ingestion, source health, service health and paginated observations.
  Duplicate source/frame identity checks payload hash before inference and returns the original
  run; changed contents produce conflict. One POST/inference at a time; no queued work.
- Source failures retain null frame/time/value instead of invented negative observations.
  Inference failures, late results, invalid provenance, unsupported capabilities and untyped
  provider responses produce typed failures. DB errors return 503 and never claim a saved result.

## Exact commands and actual outcomes

```powershell
git fetch origin
git checkout -b codex/phase-1 origin/main
.\.venv\Scripts\python.exe -m pip index versions python-fasthtml
.\.venv\Scripts\python.exe -m pip install python-fasthtml==0.14.13
.\.venv\Scripts\python.exe -m pip index versions opencv-python-headless
.\.venv\Scripts\python.exe -m pip index versions uvloop
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe tools\phase1_smoke.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m vop demo --image fixtures\scene.png --engine mock
git diff --check
```

Actual host: the same Windows 11 Pro build 26300 / Python 3.11.9 Dell from Phase 0.
All runtime dependencies installed successfully; full cross-platform offline closure pinned
in `requirements-offline.txt`. Optional OpenCV availability was checked, but it was neither
installed nor used with hardware. FastHTML signature/source and official documentation were
checked; the service disables framework CDN headers, automatic sessions and static file routes.
The proposed SRS FastAPI baseline was adapted to FastHTML for this small ASGI API; no competing
frontend or ORM was added. See ADR-0004.

The initial Phase 1 API test run had 92 passes and 14 failures because Windows asyncio's
internal socketpair was rejected by the Phase 0 blanket connect guard. A narrowly scoped
thread-local exception permits only the stdlib socketpair's loopback connect; direct sockets,
HTTP, camera and model download attempts remain blocked. Regression checks verify that both
direct loopback connects and internet `create_connection` calls are still denied in tests.

Final local automated result: **131 passed in 3.10 seconds**, no warnings. Includes original
78 Phase 0 tests, new configuration/schema/rollback/immutability/API/auth/restart/idempotency/
pagination/overload/deadline/contract/failure tests, fake HTTP/OpenCV adapter checks, and actual
spawned-child synthetic capture. `pip check`: no broken requirements. Mock CLI: exit 0 with
three labelled synthetic answers. `git diff --check`: no errors (normal LF/CRLF notices only).

`tools/phase1_smoke.py` also passed against an actual listening HTTP process, not just an ASGI
test client. It generated an ephemeral token and configuration/database, bound only loopback,
performed synthetic capture (201), verified unauthenticated denial (401), ingested a synthetic
PNG twice (201 then idempotent 200), terminated/restarted the process and confirmed **six
observations survived**. It then stopped the process and removed the temporary data. The
same script is part of CI. It prints no secret values or private camera settings.

## Acceptance results

| Gate | Local result | Evidence / limitation |
|---|---|---|
| P1-01 | PASS | JSON schema version, IDs/criteria/timeouts/source policy validated; unknown/missing/secret fields rejected; API excludes source settings. |
| P1-02 | PASS | Synthetic/file actual acquisition; fake USB/RTSP/HTTP adapter semantics; actual child IPC and deadline cleanup; live hardware not run. |
| P1-03 | PASS | Atomic DB migration/storage, immutable query versions, rollback of partial config, clean process restart, future/foreign schema refusal. |
| P1-04 | PASS | Three independent questions share a frame; interchangeable injected providers, capability checks and original native fields/provenance. |
| P1-05 | PASS | Mandatory bearer secret, constant-time comparison, all-route 401 tests, denied-access audit, no cookies/default secret/CDN; loopback actual smoke. |
| P1-06 | PASS | Source/capture/encoded-frame/observation endpoints, pagination bounds, duplicate/conflict semantics; no arbitrary URL/path registration endpoint. |
| P1-07 | PASS | Source/model/storage/timeout/contract failures visible, null failed values, zero queue, overload audit/count and responsive health. |
| P1-08 | PASS | 131 local tests and actual Windows HTTP smoke; Windows/Ubuntu Actions installation, tests, mock demo and HTTP/restart smoke all succeeded. |

## Checked GitHub Actions and delivery

Draft PR: https://github.com/VibeCoder01/VOP/pull/2, against `main`, left unmerged.
Implementation commit: `631ae412763c2bb52dfa507b54fcc8430dd70412`.
Checked [run 38433218680](https://github.com/VibeCoder01/VOP/actions/runs/38433218680):
Windows job 115420482185 and Ubuntu job 115420482646 completed with `success`, including
dependency installation, editable build, pip check, pytest, mock demo and actual HTTP/restart
smoke. No camera/model dependencies or weights were installed. This following evidence commit
changes documentation only; the implementation checked by that run is unchanged.

## Remaining limitations and explicit stop

No real camera, camera authentication, codec compatibility, GPU or new real-model inference
was tested. Phase 0 server CPU measurements remain valid historical evidence, not a claim of
new Phase 1 benchmarking. Default service uses configured deterministic mock inference.

Authentication is a single local operator bearer identity, not production roles/accounts.
All browser Origin headers are rejected; there is no browser workflow yet. Camera credentials
embedded in URL userinfo are unsupported. Network policies are operator-owned allow-lists,
not a general public URL ingestion service. No installer/background OS service is installed.

Inference is synchronous inside a worker thread with a **soft deadline**. Finite late answers
become timeout errors, and health stays responsive, but a hung injected engine holds the single
in-flight slot until it returns/process exit. Hard model cancellation/process isolation and
remote workers remain later SRS INF-011 work; unattended heavy models are not claimed safe here.
Live capture itself has a hard child deadline; raw pixels are not retained in SQLite.

Question history is immutable; migrations currently support initial schema creation only.
Future migrations require consistent backup/version matching. Retention, episode state machine,
event metrics, query/dashboard UI, alerts, camera discovery and distributed workers remain later.
Application licence remains undecided; model licensing remains separate. No secrets, real imagery,
weights, database files or private network configuration are committed.

**Phase 1 foundation gate achieved, including checked Windows/Ubuntu CI.** PR #2 remains draft
and unmerged for review. Recommendation: GO for Phase 2 review, with the limitations
above retained. Phase 2 implementation requires explicit new authorisation.
