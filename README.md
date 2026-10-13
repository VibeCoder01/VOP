# Visual Observability Platform — Phase 2 browser capability

Phase 2 adds a local browser workspace, immutable question editing, sampled temporal states,
confirmed episodes, metrics, ROI/privacy processing, explicit sampling and default-off evidence.
It began on the tested Phase 1 branch while PR #2 was open. After the owner merged PR #2,
Phase 2 was aligned with the updated `main` and its PR targets `main` directly. The SRS remains
unchanged. No Phase 3 work is authorised.

## Test the dashboard on this laptop

```powershell
# Run from your VOP checkout:
git switch codex/phase-2
.\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tools\phase2_smoke.py
.\.venv\Scripts\python.exe tools\run_dashboard.py
```

Create the venv first (`py -3.11 -m venv .venv`) for a new checkout. The smoke script uses a
temporary synthetic database/key and prints `result: PASS`. The dashboard launcher intentionally
prints a local operator key for sign-in. Open **http://127.0.0.1:8765**, paste that key into
**Access key**, and select **Open workspace**. The service runs in that terminal; Ctrl+C stops it.
The default synthetic/mock setup needs no GPU, d1-3B weights or camera. An existing `VOP_API_TOKEN`
can be used; a generated key changes on restart. Neither key is stored in the application DB.

Try **Run synthetic demo** to record six rapid, explicitly mocked samples and a closed episode.
Use **Capture once** to inspect the privacy-masked frame, optional ROI outline, native fields and
provenance. **Questions → Edit** creates a new immutable version; old observations/events keep
their original version. Binary, choice and ordinal questions validate their respective criteria.
The mock preset is a user-selected synthetic answer, not computer vision. Its per-source/version
override survives restart. Unconfigured mock questions return unsupported instead of fabricated
answers. The source and model interfaces remain independent; no remote worker transport is added.

**Sources → Edit source** controls enabled state, evidence retention and sample interval. A nonzero
interval (1–3600 seconds) explicitly starts background sampling, independent of browser tabs;
0 stops it. Saved sampling controls resume after restart. There is one worker and zero queued
frames; missed/busy samples are dropped and audited, failed sources back off up to 300 seconds.
The overview shows sampling status; use **Refresh view** to refresh the native HTML. Heavy injected
inference retains the Phase 1 soft deadline and can occupy the slot until process restart;
hard real-model isolation remains later work, not an unattended-production claim.

Temporal states are **UNKNOWN**, **INACTIVE**, **PENDING**, **ACTIVE**, **RECOVERING** (binary), or
**OBSERVED** (valid choice/ordinal). Binary activation/recovery use configurable confirmation
counts (default 2/2). Episodes start at the activation-confirmation timestamp and close only
after confirmed negatives. Error, unsupported, missing and stale samples remain UNKNOWN.
Gap policies: **resume** after reconfirmation, **split** into an interrupted/new episode without
claiming a negative end, or **manual review** (remains UNKNOWN until an operator reviews history
and saves a new version). A revised question supersedes any old open episode without fake closure.

**Events** shows the latest 100 recorded episodes. **Metrics** provides source/date/timezone
filters, counts, estimated sampled durations, rates per covered hour, occupancy/coverage,
choice dwell and ordinal SVG trends. UTC instants remain intact; timezone labels include offsets
and distinguish repeated DST hours. Date filters are local-calendar inclusive dates converted
to UTC intervals; clipping does not restart an already active episode. UNKNOWN intervals break
chart lines. No observations/eligible interval displays **No data**, not a fabricated zero.
Durations interpolate only bounded intervals with successful endpoints; they do not prove
continuous visual truth. Rates from tiny samples are not forecasts. Ordinal levels are not
physical measurement units or a universally calibrated confidence.

**Evidence is off by default.** When enabled per source, only a privacy-masked PNG preview
(up to 1920×1920, original metadata stripped) is retained in SQLite. Query ROI crops are applied
after privacy masks; compatible ROI groups share the original frame identity while preserving
all native provider outputs/usage. Source `settings.privacy_masks` is an optional list of
normalised `[x,y,width,height]` rectangles in the private operator configuration. A single masked
preview can also exist temporarily in memory for immediate inspection without retention.
Retained frames and previews require operator access; viewers get 403. Deletion removes the BLOB,
clears the matching in-memory preview and checkpoints SQLite with secure deletion enabled.
It cannot retract copies already made by users or externally managed backups.

Browser login uses a signed HttpOnly/SameSite=Strict one-hour cookie; write forms require CSRF
and same-origin checks. Optional read-only access uses a distinct `VOP_VIEWER_TOKEN` set before
startup (same 32–256 ASCII-character requirement). Viewers can inspect metadata/metrics, but cannot
capture, edit, sample or access image evidence. There are no individual user accounts or SSO.
Bearer API access continues to work. No key-in-URL login, external scripts/CDNs, SPA or frontend
build tooling is used. Templates escape user text, and CSS respects reduced motion.

Additional authenticated APIs: `GET /api/v1/events`, `GET /api/v1/metrics`, `POST /api/v1/replay`.
**Settings** also permits an idle, operator-requested deterministic replay. SQLite schema v2
upgrades v1 transactionally, retaining observations and making a consistent
`<database>.v1-backup.sqlite3` before migration. Existing UI revisions/controls win over unchanged
bootstrap config on restart. New declared config versions can be activated; historical versions
cannot be edited. Late frames are retained/audited but excluded from live state/event replay.

## Authorised USB test and remaining hardware limits

The owner authorised a brief USB test on this Dell. Index 0 returned a real **640×480 PNG**.
Two subsequent USB captures traversed mock inference, storage and dashboard rendering: six
observations, HTTP 200 dashboard, mock ACTIVE binary state. **No camera pixels were retained
or committed, and no real-model inference ran.** This validates capture/software, not model
accuracy. Tapo/RTSP hardware is untested because no authorised endpoint/configuration was supplied.

For an explicitly authorised future USB session, install `.[camera]`, prepare ignored
`config.local.json` with kind `usb` and `settings: {"device":0}`, and run:

```powershell
.\.venv\Scripts\python.exe tools\run_dashboard.py .\config.local.json --allow-live-sources
```

Startup/sample controls never bypass the live-source opt-in. Network-camera endpoints remain
environment references with exact allowed-host policy; do not paste credentials into repo/UI.
Real d1-3B CPU feasibility remains the separately recorded Phase 0 server result; no GPU,
remote-worker, model-format or accuracy claim is added. See `CODEX_PHASE_2.md` and
`reports/phase2-validation.md` for gates, actual commands and limitations. Licence decisions
remain separate. Stop after Phase 2; Phase 3 requires explicit authorisation.

## Phase 1 historical foundation (v0.2)

The following section describes the earlier Phase 1 baseline. Browser sessions, retained evidence
and schema v2 above supersede its historical no-cookie/no-pixel statements in the current build.

Phase 1 adds validated JSON configuration, a local authenticated service, SQLite observations
and one-shot source adapters to the merged Phase 0 inference contracts. `CODEX_PHASE_1.md`
records the current foundation scope; `SRS-v0.2.md` remains the product specification.
The default pipeline is explicitly **MOCK — no vision**. Model weights are never downloaded
or loaded by service startup. Phase 0 benchmark evidence remains in the existing reports.

### Phase 1 operator quickstart (PowerShell, historical)

```powershell
git switch codex/phase-1  # Until the Phase 1 PR is merged
.\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -q
# Actual HTTP/restart smoke with temporary token/database; no internet or camera:
.\.venv\Scripts\python.exe tools\phase1_smoke.py
```

Create the venv first with `py -3.11 -m venv .venv` if this is a new checkout. Start a persistent
local service and exercise it from the same PowerShell session without putting the token in
a file or command-line argument:

```powershell
$env:VOP_API_TOKEN = & .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))"
$service = Start-Process -FilePath (Resolve-Path .\.venv\Scripts\python.exe).Path -ArgumentList '-m vop serve --config sample-config/phase1.json --port 8765' -WindowStyle Hidden -PassThru
$headers = @{ Authorization = "Bearer $env:VOP_API_TOKEN" }
# Wait for startup, without displaying the secret:
for ($attempt = 0; $attempt -lt 50; $attempt++) {
    try { $health = Invoke-RestMethod http://127.0.0.1:8765/api/v1/health -Headers $headers -TimeoutSec 2; break }
    catch { Start-Sleep -Milliseconds 200 }
}
Invoke-RestMethod http://127.0.0.1:8765/api/v1/sources -Headers $headers
Invoke-RestMethod http://127.0.0.1:8765/api/v1/sources/synthetic-scene/capture -Method Post -Headers $headers
Invoke-RestMethod 'http://127.0.0.1:8765/api/v1/observations?limit=20' -Headers $headers
# Also accepts encoded JPEG/PNG bytes; frame ID enables safe duplicate detection:
Invoke-RestMethod http://127.0.0.1:8765/api/v1/sources/synthetic-scene/frames -Method Post -Headers (@{Authorization=$headers.Authorization; 'X-Frame-ID'='manual-frame-1'}) -ContentType image/png -InFile .\fixtures\scene.png
# When finished:
Stop-Process -Id $service.Id
```

Alternatively run `python -m vop serve --config sample-config/phase1.json --port 8765` in the
foreground with the same environment secret. The CLI binds **127.0.0.1 only** and all routes
require a 32–256 character ASCII bearer secret. There are no cookies, default credentials,
public health exceptions, account management or permissive CORS. This is a single-operator
development foundation, not a production multi-user authentication system. Rotate the secret
by restarting with a newly generated value; it is never stored in the database or logged.

The sample produces three independent questions over one generated shape image. Capture returns
201 with a run ID, stable source/frame/question provenance, native fields, UTC timestamps and
`synthetic: true`. Persisted observations survive restart; no pixels are saved. SQLite stores
frame metadata, immutable question versions, runs, individual answers and minimal audit events.
Changing question content requires a new version. The initial schema migrates transactionally;
unknown/newer schemas are rejected. Before a future migration, stop the service and back up the
database with SQLite's backup API; do not copy an active WAL database file alone. Roll back by
restoring that backup and the matching application version; no downgrade is attempted.

Endpoints: authenticated `GET /` (diagnostic HTML), `GET /api/v1/health`,
`GET /api/v1/sources`, `POST /api/v1/sources/{id}/capture`,
`POST /api/v1/sources/{id}/frames`, and `GET /api/v1/observations`.
Observation pagination uses `limit` (1–100) and `after` (last sequence); optionally filter by
configured `source_id`. Byte ingestion accepts only JPEG/PNG and at most 20 MiB. A repeated
source/frame ID returns the original result without inference; changed content under that ID
returns 409. A failed capture has **null frame/capture timestamp and null values**, not a fake
image or confirmed negative. Binary answers use positive/negative; valid choice/ordinal answers
have `normalised_state: not_applicable`, without pretending they are binary decisions.

One POST is admitted at a time, with no queued frames; excess work returns 429 and is audited.
Health remains responsive during inference. Capture and inference identities stay independent;
the service never silently substitutes a model. `create_app(settings, engine=...)` accepts an
explicitly prepared engine implementing the Phase 0 protocol, so model code and hardware remain
outside callers. The CLI intentionally uses configured mocks; optional real-model preparation
continues through the explicitly consented Phase 0 tooling. Synchronous inference deadlines are
soft: late results become timeout failures, but a hung injected engine cannot be killed by this
service. Process-isolated real inference/remote workers remain later work; do not deploy this
foundation for unattended heavy models. No new real-model run occurred in Phase 1.

## Optional one-shot camera inputs

Camera inputs require operator-owned `config.local.json` (ignored), explicit
`--allow-live-sources`, and the same authenticated POST capture endpoint. Startup never opens
a device; there is no continuous capture or scheduler. Configuration is read from the local
file, not accepted through an HTTP registration API. Supported source kinds:

| Kind | `settings` | Additional requirement |
|---|---|---|
| `synthetic` | `{}` | No hardware; generated shapes |
| `file` | `{"path":"fixtures/scene.png"}` | Path relative to the configuration file |
| `usb` | `{"device":0}` | Optional OpenCV installation |
| `rtsp` | `{"endpoint_env":"VOP_CAMERA_URL","allowed_hosts":["camera.example"]}` | Optional OpenCV; endpoint set locally in environment |
| `snapshot` | Same environment reference/host list | Stdlib HTTP(S) acquisition |

Use authorised local hostnames in private configuration; the table's hostname is fictional.
Camera URLs and query credentials belong only in the referenced environment variable, not
source control. Userinfo credentials in URLs are rejected. Username/password camera
authentication, discovery and arbitrary redirects are deliberately unsupported at this stage.
Only exact configured hostnames/schemes are allowed; HTTP redirects and inherited proxies are
disabled. The API returns no endpoint, environment-reference or local-path settings.

```powershell
# Only for USB/RTSP adapter use; not installed in CI:
.\.venv\Scripts\python.exe -m pip install -e '.[camera]'
# Explicit live capture consent (foreground example):
.\.venv\Scripts\python.exe -m vop serve --config .\config.local.json --allow-live-sources
```

USB/RTSP/HTTP acquisition runs in a spawned child with a hard total deadline; blocked reads
are terminated and persisted as typed failures. Native camera diagnostics are suppressed to
avoid exposing endpoints. Adapter behaviour is tested with fakes; **no real camera was connected**.
Optional OpenCV installation/version availability is checked separately; codec/hardware support
is not claimed. The allow-list is for operator-controlled destinations, not a general public
URL ingestion service; production DNS/transport and credential policy remain deployment work.

FastHTML/Starlette supplies the local API and diagnostic HTML; SQLite uses the standard library.
There is no React app, dashboard, temporal state machine, event metric, alert, remote transport,
installer, licence selection or Phase 2 implementation. See `reports/phase1-validation.md`.
All 131 local tests passed, and the checked [Windows/Ubuntu Actions run](https://github.com/VibeCoder01/VOP/actions/runs/38433218680)
passed installation, tests, mock demo and actual HTTP/restart smoke on both platforms.

## Phase 0 historical setup and evidence

## Windows 11 setup (PowerShell)

Use 64-bit Python 3.11. The offline stack was tested on Python 3.11.9 / Windows 11 Pro
build 26300 on the Dell Latitude 5510 / i5-10310U. Installation needs internet or a wheelhouse;
tests and demo need no internet, model dependencies, weights, GPU or credentials.

```powershell
git clone https://github.com/VibeCoder01/VOP.git
Set-Location VOP
# Until merged, select the implementation branch:
git switch codex/phase-1
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pip check
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m vop demo --image .\fixtures\scene.png --engine mock
.\.venv\Scripts\python.exe -m vop check-env
```

Expected: tests pass; `pip check` finds no broken requirements; demo exits 0 with
`synthetic: true`, `engine_id: mock`, the label `MOCK — no vision` and three independent
answers sharing one `frame_id`. The mock returns configured values, never examines pixels.
`check-env` prints OS/build, CPU, RAM, disk and dependency versions. Controller inventory
does not establish accelerator runtime compatibility.

The offline dependency closure and build backend are pinned in `requirements-offline.txt`.
For air-gapped installation, populate a wheelhouse on the same Python/OS/architecture with
`python -m pip download -r requirements-offline.txt -d wheelhouse`, then install with
`--no-index --find-links wheelhouse -r requirements-offline.txt`. Editable installation uses
the installed backend without dependency downloads. The abstract-shape fixture can be recreated:

```powershell
.\.venv\Scripts\python.exe .\tools\generate_fixture.py
```

## Portable contracts

`FrameEnvelope` carries image bytes, source/frame IDs, SHA-256, dimensions and UTC timestamps.
Only `FileImageAdapter` accepts a path. JPEG/PNG are detected by contents and fully decoded;
missing, unsupported and corrupt inputs raise typed `ProviderError`. Imported file capture
time is unknown: `captured_at_utc` explicitly uses the import instant.

`QuestionSpec` declares kind, version, criteria and binary threshold. An `InferenceRequest`
groups independent questions over one frame and optional UTC deadline. Callers use
`InferenceEngine` and `infer(engine, request)`, without model classes, paths or device assumptions.
Two mock engine instances are interchanged through that caller in offline tests. Capabilities
and engine identity are independent of source IDs. Future GPU/CPU or remote engines can
implement the same interface; transport, scheduling and automatic fallback remain deferred.

`InferenceResult` retains source/frame/question provenance, capture/completion timestamps,
elapsed time, native outputs, usage, revision and explicit `success`, `unsupported`, `timeout`
or `model_failure`. Failed answers have `value: null`, never fabricated negatives. Binary
scores retain their threshold and `calibrated: false`; choice confidence and ordinal expected
levels preserve distinct semantics and all native fields/extensions. This is not an accuracy
or temporal-measurement implementation. Synchronous deadlines are checked before/after calls;
only the benchmark child has a hard timeout that interrupts execution.

## Optional benchmark — explicit operator action

The [official API/source](https://huggingface.co/LiquidAI/d1-3B/blob/051bcc464b01b9f92942b364d9586b0ef5912432/README.md)
was inspected at SHA `051bcc464b01b9f92942b364d9586b0ef5912432`. Runtime validation and
measurements are recorded in `reports/`; source inspection alone is not a successful model run.
`requirements-liquid.txt` contains separately installed direct runtime pins. The validated
Linux x86_64 / Python 3.14.4 CPU closure is in `requirements-liquid-linux-cpu.lock.txt`;
the optional Windows model runtime remains unvalidated.

The Dell inventory showed about 5.4 GiB available RAM and 14.5 GiB free disk. These are inventory
readings, not measured model usage. Its inference outcome remains `not_run`; CPU-model feasibility
on the Dell cannot be inferred from a run on another machine. An independently provisioned
server can run this same CLI; its measurements must remain separately labelled.

Inspect inventory and generate a declined-consent report (no download; expected exit 2):

```powershell
.\.venv\Scripts\python.exe -m vop check-env
.\.venv\Scripts\python.exe -m vop benchmark --engine liquid-d1-3b --image .\fixtures\scene.png --reference-dell
```

Only if choosing to install the runtime and accept resource/checkpoint-code risks:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-liquid.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m vop check-env
Remove-Item Env:HF_HUB_OFFLINE -ErrorAction SilentlyContinue
Remove-Item Env:TRANSFORMERS_OFFLINE -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m vop benchmark --engine liquid-d1-3b --image .\fixtures\scene.png --reference-dell --allow-model-download --accept-model-risk --timeout-seconds 900 --repeats 3
```

Both consent flags are required; without both, `not_run` is recorded and no child starts.
Consent includes downloading several GB and executing checkpoint Python with
`trust_remote_code=True`. Only the pinned official snapshot is accepted; the adapter loads it
locally with pinned code, `local_files_only=True`, `dtype=torch.float32` and `.to('cpu')`.
Internal tokenizer/processor lookups use that snapshot too. Calls use
`model.system_one(None, questions, images=[image])`, mapping binary → noul, choice → choice,
ordinal → score. No chat generation, silent FP16 conversion or Vulkan runtime is used.

Preflight conservatively requires **16 GiB available RAM** and **20 GiB free cache disk**;
these are experiment thresholds, not safety guarantees or measured requirements. A nominal
16 GiB laptop usually fails the RAM threshold. FP32 weights alone are estimated at about
12.5 GB before runtime overhead. After reviewing the risk, an operator may add
`--override-preflight` for that one command. This never disables the watchdog or 2 GiB reserve.
Another local cache disk can be selected with `--cache-dir D:\VOP-model-cache`.
`--reference-dell` rejects a mismatched host; omit it for a separately labelled server run.

The child has a total download/load/inference timeout. It is stopped if sampled available
RAM falls below 2 GiB or process-tree RSS exceeds starting available RAM minus the reserve.
100 ms sampling can miss peaks; RSS is not total committed memory, and this cannot guarantee
protection from pagefile stress or sudden allocations. Partial results survive failures.

Reports distinguish `not_run`, `blocked_preflight`, `passed`, `failed_oom`, `failed_dependency`,
`failed_runtime` and `failed_timeout`. Actual runs record revision/cache path and hub blob hashes
where available, dependency versions, image hash/dimensions, separate download/load timings,
sampled peak working set and minimum available RAM, and actual raw/normalised outputs for
1/3/5 questions. Each shape has a first call and at least three warm samples, median/maximum.
The 1-question first call is first ever inference; 3/5-question calls follow earlier cases.
p95 remains null below 20 warm samples (`--repeats 20`). Timings include adapter validation.
`passed` means valid API output, not validated speed or accuracy.

Reports default to ignored `reports/local/`. Review generated paths/log tails before sharing.
Exit codes: successful demo/check-env 0; image/CLI failure 1; benchmark passed 0, otherwise 2;
argument misuse 2. Synthetic mock outputs are never included as real benchmark evidence.

## Actual alternate-server CPU result

The owner accepted alternate-server CPU feasibility as sufficient for Phase 0. The official
FP32 benchmark **passed**, with 12 valid calls over the same 384×256 synthetic image. All floating
parameters were separately verified as `torch.float32` on CPU (3,123,483,888 parameters).

| Questions | First call | Warm median | Warm maximum | Warm samples |
|---|---|---|---|---|
| 1 | 8.526 s | 6.745 s | 6.746 s | 3 |
| 3 | 9.473 s | 9.437 s | 9.485 s | 3 |
| 5 | 11.380 s | 11.307 s | 11.394 s | 3 |

Model-load stage: 1.294 s after download; download/cache resolution: 125.336 s. First inference
includes lazy runtime/processor setup outside the load stage. Sampled process-tree peak RSS:
**17.700 GiB**; minimum available RAM: 26.779 GiB. Sampled child-tree swap peaked at 328.422 MiB,
below the 512 MiB watchdog threshold; this is not zero paging. Linux child-tree swap above
that threshold produces `failed_oom`; Windows per-process swap is not measurable by this tool.
These results support sparse still images on this server. Median throughput is approximately
0.148/0.106/0.088 images per second for 1/3/5 questions, derived from recorded median latency.
GPU and Dell performance remain unmeasured. See `reports/alternate-server/phase0-report.json`
and `.md` for actual native outputs. **GO** for Phase 1 foundation review under the accepted
server criterion; Phase 1 work itself still requires explicit authorisation.

For a matching Linux CPU environment, create a venv and install
`requirements-liquid-linux-cpu.lock.txt`, then install the package with
`python -m pip install --no-deps --no-build-isolation -e .`. Run the same benchmark command
with Linux paths and without `--reference-dell`. This is standalone CLI execution, not a worker
deployment service. Without ensurepip, use `python3 -m venv --without-pip .venv`, then
`python3 -m pip --python .venv/bin/python install pip -r requirements-liquid-linux-cpu.lock.txt`.

## Evidence, decisions and limits

- `reports/phase0-report.json` / `.md`: Dell inventory and honest feasibility outcome.
- `reports/phase0-validation.md`: commands, results, changed files and all ten acceptance criteria.
- `decisions/ADR-0003-phase0-feasibility.md`: Phase 0 recommendation and real-engine decision.
- `.github/workflows/offline-tests.yml`: Python 3.11 tests on Windows/Ubuntu. Setup fetches only
  offline dependencies; test sockets are denied, Torch is absent and models are never downloaded.
  Both jobs passed in the checked [initial PR run](https://github.com/VibeCoder01/VOP/actions/runs/38429400246).

Model load, throughput and workload accuracy must be validated before choosing a production
engine. A server benchmark does not prove Dell feasibility. Alternative models/runtimes require
explicit image/API-equivalence, licensing and accuracy checks through the same contracts.
Capture, inference, storage and UI placement remain independent; no distributed service is built.

The application licence remains **undecided**. The model's
[checkpoint licence](https://huggingface.co/LiquidAI/d1-3B/blob/051bcc464b01b9f92942b364d9586b0ef5912432/LICENSE)
requires independent review before intended use/redistribution. No model weights, credentials,
real camera images or private network configuration are committed. Repository visibility remains
unchanged. The SRS and accepted ADRs remain the architectural baseline.

**Phase 2 is authorised; Phase 3 requires explicit new authorisation.**
