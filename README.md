# Visual Observability Platform — Phase 0

Provider-neutral still-image CLI, deterministic **MOCK — no vision** engine, offline tests
and an optional guarded LiquidAI/d1-3B CPU benchmark. `CODEX_PHASE_0.md` controls this phase;
`SRS-v0.2.md` remains the product specification. No dashboard, database, camera capture,
remote worker transport or Phase 1 service is implemented.

## Windows 11 setup (PowerShell)

Use 64-bit Python 3.11. The offline stack was tested on Python 3.11.9 / Windows 11 Pro
build 26300 on the Dell Latitude 5510 / i5-10310U. Installation needs internet or a wheelhouse;
tests and demo need no internet, model dependencies, weights, GPU or credentials.

```powershell
git clone https://github.com/VibeCoder01/VOP.git
Set-Location VOP
# Until merged, select the implementation branch:
git switch codex/phase-0
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
  CI success is reported only after checked execution.

Model load, throughput and workload accuracy must be validated before choosing a production
engine. A server benchmark does not prove Dell feasibility. Alternative models/runtimes require
explicit image/API-equivalence, licensing and accuracy checks through the same contracts.
Capture, inference, storage and UI placement remain independent; no distributed service is built.

The application licence remains **undecided**. The model's
[checkpoint licence](https://huggingface.co/LiquidAI/d1-3B/blob/051bcc464b01b9f92942b364d9586b0ef5912432/LICENSE)
requires independent review before intended use/redistribution. No model weights, credentials,
real camera images or private network configuration are committed. Repository visibility remains
unchanged. The SRS and accepted ADRs remain the architectural baseline.

**Stop at Phase 0. Phase 1 requires explicit authorisation.**
