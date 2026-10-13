# Codex implementation contract — Phase 0

**Handoff revision:** 0.2.1 (SRS baseline remains v0.2)  
**Status:** Ready for implementation; requires execution on the user's Dell to establish actual model feasibility  
**Reference:** `SRS-v0.2.md` (especially §§1–2, 6, 8–9, 12, 14–15 and Appendix A)  
**Target hardware:** Windows 11, Intel Core i5-10310U, 16 GiB nominal installed RAM, CPU-only.  
**Time boundary:** Phase 0 ends at a reproducible feasibility report and a small CLI vertical slice. It is not the full MVP.

## Objective

Prove that a *single still image* can pass through a source-frame abstraction to a provider-neutral inference contract; verify LiquidAI/d1-3B's official `system_one` API when physically possible; quantify CPU memory and latency; and leave an offline, deterministic test suite runnable without external services. The application may be judged technically sound even if full-precision d1-3B **does not fit this laptop**.

## Explicit scope

1. Create a minimal Python project with `src/vop/` and `tests/`; install instructions and PowerShell commands. Use a virtual environment. Avoid a broad framework scaffold.
2. Define and test typed `FrameEnvelope`, `QuestionSpec`, `InferenceRequest`, `InferenceResult` and `ProviderError` records. Keep `captured_at_utc` distinct from `processed_at_utc`. Store an explicit state for success, unsupported, timeout and model failure. Use local file paths only in the initial implementation.
3. Implement a `FileImageAdapter` that reads a saved JPEG/PNG image. Verify corrupt/missing-file behaviour. Produce deterministic synthetic example fixtures with Pillow if needed; no real camera images in the repository.
4. Implement a **clearly labelled mock inference engine**. It must take preconfigured deterministic answers, not pretend to perform computer vision. Validate multiple independent questions sharing the same frame ID. This allows CI to succeed without downloading a model.
5. Implement an optional `LiquidD1InferenceAdapter` that uses official `AutoModel.from_pretrained(..., trust_remote_code=True, dtype=torch.float32).to('cpu')` plus `model.system_one(None, questions, images=[image])` on Windows CPU. Map `binary → noul`, `choice → choice`, `ordinal → score`; preserve raw provider answer and `usage`. Pin the exact checkpoint commit after validation, and record the Python/Transformers/Torch versions used. The model is **not** a text-generating chat API.
6. Implement CLI commands `demo` (offline mock and image), `check-env` (machine and memory inventory), and `benchmark` (opt-in real-model benchmark). Exact CLI argument spelling may be adapted, but keep the commands and documented examples stable. `demo` must never download weights. `benchmark` must never run by default.
7. Write both `phase0-report.json` (machine-readable) and `phase0-report.md` (human-readable) for the attempted real-model benchmark. Reports must distinguish `not_run`, `blocked_preflight`, `passed`, `failed_oom`, `failed_dependency`, `failed_runtime`, and `failed_timeout` outcomes. Do not fill missing measurements with zeros or estimated values.

## Cross-host compatibility guardrail (design-only in Phase 0)

The reference Dell (i5-10310U, 16 GB RAM, Windows 11) is solely a CPU feasibility target. Future deployments must permit camera capture, web/dashboard services, event storage, and inference to run on different machines. For example, the Dell could capture frames and serve the dashboard while a different model, d1-3B, or a GPU-accelerated model executes on `antec`. The remote implementation remains **Later** under SRS INF-011 / OPS-010.

For this phase, keep the `InferenceRequest` and `InferenceResult` **independent of model device and process location**. A file path is valid as a Phase 0 *local image adapter input*, but it must not be a mandatory shared path assumed usable by all inference providers. The frame payload should be obtainable by the provider adapter via a documented resolver or byte-oriented representation; carrying actual image data over a network is a later task. The inference caller shall depend on an abstract engine contract, not import model-specific Torch classes or call `.to('cpu')` itself. Runtime placement belongs in per-engine configuration and the future scheduler, not in the generic question or source schema.

Use the existing deterministic mock engine to demonstrate interchangeability of two provider instances (or a simple alternate mock provider), using exactly the same request/response types. This is an **offline contract test only**: do not create HTTP/gRPC servers, remote workers, RPC frameworks, credentials or network tests in Phase 0. If the real d1-3B CPU benchmark fails, report the finding without disabling alternative local or future remote inference engines.



## Mandatory non-goals

No web dashboard, UI framework, persistent database, continuous video pipeline, RTSP/ONVIF connectivity, multiple live cameras, security/alerts, installer, automated background service, camera discovery, production flood detector or work deployment. Those are subsequent phases. A one-off USB/RTSP *manual* experiment can be documented separately but is **not** required for Phase 0 acceptance.

## Feasibility workflow

A. First, run offline tests using a mock provider; verify the contract and errors. The tests must run on a CI worker without internet or model weights.

B. On the target Windows laptop, run `check-env` before any model attempt. Record: Windows build, CPU, total/available physical RAM, Python version, architecture, Torch/Transformers versions, free disk space and whether a supported accelerator is present (expected: CPU). Do not assume that 16 GB installed means 16 GB available.

C. Warn and **do not auto-run** the model if available memory or storage is inadequate for safe experimentation. Offer an explicit operator override that is local to the command; a benchmark must never silently exhaust all system RAM. Record when the operator declines. An opt-in isolated child process and a bounded execution time are preferred; record OOM/pagefile stress as a failure, not a success. No fixed memory threshold is claimed to guarantee safety.

D. Download the official model only after the operator chooses to run `benchmark`. Record source, resolved commit SHA, download/cache path and hashes where available. Never use an unverified third-party quantised conversion as though it were official. Never commit model files.

E. Run a single image with 1, 3 and 5 named questions, first-call and warmed-call timings where feasible; at least three steady-state repeats per case, subject to CPU practicality. Record image dimensions/sha256, one run per count, sample counts and latency statistics (median and maximum; p95 only if sufficient repetitions). Capture peak process-tree RSS/working set and available memory, as measurable on the platform. If the model cannot load, report why and stop, preserving the offline mock demonstration.

F. Validate the returned top-level `answers` and `usage` structure and native answer fields using actual output. For `noul`, record returned score without claiming a calibrated real-world false-alarm rate; for `choice`, inspect `choice`/`confidence`/`probabilities`; for `score`, inspect `score`/`confidence`/`probabilities`/`legend`. Keep provider outputs as received and wrap them in stable internal typed results.

G. Do not silently switch CPU execution to FP16, GGUF or another provider. If FP32 fails, record alternatives with links and an explicit compatibility test proposal. API-equivalence, image support and licensing must be verified before adopting any alternative.

## Acceptance gates (all required unless marked optional)

| ID | Evidence needed | Pass rule |
|---|---|---|
| P0-01 | Git project structure and Windows setup commands | Fresh checkout can create venv, install locked *offline-test* dependencies and run tests per instructions. |
| P0-02 | Mock CLI invocation and synthetic fixture | Command exits 0, shows clearly labelled mock results and shared frame ID for ≥2 questions. |
| P0-03 | Adapter contract tests | Binary/choice/ordinal mapping and malformed/unsupported answer cases tested without model download; same request/result types work with two interchangeable mock provider instances, without requiring shared filesystem or device-specific assumptions in the caller. |
| P0-04 | Error handling tests | Missing/corrupt image and inference exceptions yield typed errors, never a fabricated `negative`. |
| P0-05 | Opt-in real-model launcher | Has clear operator confirmation/flag, memory warning, timeout, pinning and no CI download path. |
| P0-06 | Feasibility report | Includes actual environment, attempted model/commit, explicit outcome and metrics or nulls with reason; no fabricated measurements. |
| P0-07 | Documentation | README has exact PowerShell commands, expected outputs, known limitations, licensing note and next-step recommendation. |
| P0-08 | CI / offline tests | CI passes without model weights, camera hardware, secrets or network access during tests. |
| P0-09 | Actual d1-3B invocation (**conditional hardware test**) | On the Dell, records real output and measurements if feasible; if blocked or failed, status is honestly recorded, not converted into a CI failure or a false pass. |
| P0-10 | Phase review | Finish with `GO`, `CONDITIONAL GO` or `NO-GO`, including why and whether Phase 1 should use d1-3B or another engine. |

`P0-09` is a **hardware feasibility result**, not a gate requiring the full-precision model to succeed. A reproducible failure is a valid technical finding. Completion of the software prototype requires P0-01 to P0-08 and P0-10.

## Suggested command UX (interface, not a claim that these commands already exist)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m vop demo --image .\fixtures\scene.png --engine mock
.\.venv\Scripts\python.exe -m vop check-env
# Explicit opt-in; may download several GB; run only on the actual test machine:
.\.venv\Scripts\python.exe -m vop benchmark --engine liquid-d1-3b --image .\fixtures\scene.png --allow-model-download
```

The benchmark command shall refuse silent downloads, explain RAM risks, and report missing dependencies clearly. If installed test dependencies are deliberately separate from inference dependencies, document a second explicit install command.

## Expected output tree after Codex implementation

```text
AGENTS.md
README.md
SRS-v0.2.md
CODEX_PHASE_0.md
pyproject.toml
src/vop/__init__.py
src/vop/__main__.py
src/vop/contracts.py
src/vop/inputs/file_image.py
src/vop/inference/mock.py
src/vop/inference/liquid_d1.py
src/vop/benchmark.py
tests/test_contracts.py
tests/test_file_image.py
tests/test_mock_inference.py
tests/test_error_paths.py
fixtures/scene.png       # synthetic, non-sensitive
reports/phase0-report.json  # generated locally, optional to commit if non-sensitive
reports/phase0-report.md    # actual results / outcomes, never invented
```

File names may be adapted when justified. Interfaces and separation of concerns are more important than superficial folder names.

## Hand-off to the next phase

Provide a brief architecture decision record naming the validated d1-3B runtime or the chosen fallback. Explicitly state whether the deployment can run with CPU-only inference, whether RAM is sufficient, the throughput observed, and which remaining tasks are needed before live camera integration. **Stop at this point.**
