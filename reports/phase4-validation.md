# Phase 4 implementation and validation

Owner authorised implementation on 13 October 2026 and explicitly authorised temporary
suspension/restoration of antec's existing llama workload. Recommendation: **CONDITIONAL GO
for supervised software testing; live-camera accuracy acceptance remains pending**.
No unattended worker deployment or Phase 5 work has been performed.

## Implemented scope and changed files

- `src/vop/worker.py`, `worker_protocol.py`, `inference/remote.py`: authenticated loopback
  worker, SSH-compatible transport, pinned engine identity, bounded image/protocol limits,
  one inference slot, no queue, expiring result cache, hard child deadlines and restart cooldown.
- `src/vop/secrets.py`, `integration_ui.py`, `inputs/sources.py`: Windows user-bound DPAPI
  credentials, operator forms, repeatable Tapo credential updates, local connection tests,
  private endpoint allow-list and C200/C210/C510W profiles. Linux dashboard secret storage
  requires an unlocked OS Secret Service; that OS integration was not hardware validated.
- Configuration, service, dashboard, pipeline and release export modules: explicit engine
  selection independent of sources, runtime-only transmission consent, privacy processing
  before inference, honest worker health and preserved historical provenance.
- `inference/liquid_d1.py`, manual GPU benchmark, worker/dashboard launch tools and CUDA lock:
  explicit CPU FP32 / NVIDIA CUDA precision selection without GPU dependencies on the laptop.
- Phase 4 tests, HTTP smoke/soak tools, subprocess cleanup helper, installer, release builder,
  CI workflow, version 0.5.0, README, changelog and authorised phase plan.

## Actual GPU evidence

Official LiquidAI revision: `051bcc464b01b9f92942b364d9586b0ef5912432`.
Antec: NVIDIA GeForce RTX 5060 Ti, 16 GB, compute capability 12.0; driver 595.99.02.
Dedicated Python 3.14.4 environment: Torch 2.14.1+cu130, CUDA runtime 13.0,
Transformers 5.19.0, Accelerate 1.15.0, BF16, all model parameters on `cuda:0`.
See `phase4/gpu-report.json` for actual native outputs and repeated measurements.

Load took 2.295 seconds. First one-question call took 1.780 seconds; warmed one-question
median was 31.064 ms. Peak allocated VRAM was 6,299,108,864 bytes; peak reserved VRAM
6,314,524,672 bytes. Peak host RSS was 6,079,926,272 bytes, measured child swap zero.
These are a small synthetic still-image benchmark, not camera throughput promises.

Two initial attempts against the historical cache on tmpfs stopped at the swap guard before
inference. Existing cached weights were copied to the durable application cache; no new
checkpoint was downloaded. `phase4/gpu-attempt1.json` retains the initial failure.
Historical CPU FP32 evidence was compared with BF16 fixture outputs in
`phase4/precision-comparison.json`; discrete answers agreed, native ordinal values differed.
This does not establish accuracy on live cameras or calibrated score equivalence.

Actual laptop → SSH tunnel → application-authenticated antec GPU → typed response passed.
`phase4/remote-gpu.json` includes the exact human-presence query on the synthetic fixture,
actual device/precision, round-trip timing and real native outputs. The temporary worker and
tunnel were stopped; `llama-mtp.service` was restored. The retained environment/cache supports
manual launch. Concurrent operation with the existing llama workload is not accepted:
the BF16 worker conservatively requires 8 GiB free VRAM; that workload leaves about 6 GiB.

Accelerate 1.12.0 initially installed was replaced with verified 1.15.0 after the dependency
scan identified GHSA-4j2p-28q2-5m79. The model benchmark and remote proof were repeated after
the update. The final 74-package CUDA lock had no findings in the observed OSV scan
(`phase4/cuda-dependency-audit.json`); this does not audit drivers or model code.

## Commands and observed results

Windows PowerShell, repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools\phase1_smoke.py
.\.venv\Scripts\python.exe tools\phase2_smoke.py
.\.venv\Scripts\python.exe tools\phase3_smoke.py
.\.venv\Scripts\python.exe tools\phase4_smoke.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe tools\build_release.py
.\.venv\Scripts\python.exe tools\phase4_soak.py --seconds 3600 --output reports\phase4\soak-report.json
```

199 offline tests passed after the final wire-answer validation checks. HTTP smoke checks passed for phases 1–4; persisted counts after
restart were respectively 6, 21, 18 (backup/restore), and 3. Phase 4 uses a real HTTP mock
worker and actual Windows DPAPI, no weights or cameras. Disconnect produced UNKNOWN/ERROR
without fallback. Hard timeout/process kill/restart, wrong bearer/worker identity, expiry,
payload limits, credential retry, consent reset and viewer restrictions are tested.
`pip check` reported no broken requirements.

Fresh Windows development ZIP installation and its Phase 4 smoke passed in a new temporary
environment. Browser QA used a separate disposable dashboard and explicitly synthetic worker:
sign-in, camera credential form, engine selection and health worked, with a fitting 390px
mobile layout. No fictional camera endpoint was contacted.

Windows and Ubuntu jobs passed in the observed [Phase 4 CI run](https://github.com/VibeCoder01/VOP/actions/runs/38481123375)
for the initial implementation commit `f32503c`. The final wire-answer validation refinement
is also locally verified; its subsequent CI result will be recorded after completion.
The 60-minute synthetic overload run remains in progress. No pending check is claimed passed.

The 35-package offline dependency scan had no known OSV findings at 22:59 UTC
(`phase4/offline-dependency-audit.json`). Browser QA also performed a successful synthetic
capture through the HTTP mock worker, switched back to local mock, and verified that a
plaintext LAN worker URL produces the intended explanatory HTTP 400 page. Its console error
for that deliberately invalid request was expected; no application script failure was seen.

## Pending hardware/acceptance gates

No C200 or C210 endpoint/credentials have yet been provisioned through the owner GUI during
this validation. C510W is temporarily unavailable per owner. No Tapo connection, firmware
compatibility, live camera → GPU inference, camera soak or accuracy result is claimed.
The prior USB test remains historical mock-inference evidence; it was not repeated here.
No labelled positive/negative/difficult camera dataset or owner accuracy targets exist yet.
P4-05/P4-06 and live portions of P4-07 therefore remain pending.

AMD Radeon AI PRO R9700, ROCm/Vulkan, GPU pooling, Dell real-model feasibility and a new CPU
model benchmark were not tested. The earlier antec CPU report remains historical evidence.
No OS, driver, permanent service configuration, alert destination or automatic startup changed.

Next: enter C200/C210 camera-account credentials in the local setup screen and deliberately
test connectivity; agree a resource window for the GPU worker, then validate privacy-processed
frames and labelled human-present/absent/difficult examples. Recover and test C510W separately.
Complete these Phase 4 gates before recommending broader deployment or seeking Phase 5 approval.
