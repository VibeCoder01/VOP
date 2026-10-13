# Phase 0 validation and delivery — 13 October 2026

Branch: `codex/phase-0`, based on `main` commit `0dcca1dbbfb412d9c3ce212c97e3d4573a66abbf`.
The initial local folder had only Git metadata; fetching the existing repository restored
the reviewed handoff documents. The GitHub repository itself was not empty. Visibility was
left unchanged. No SRS requirements or IDs were redesigned.

## Actual local execution

```powershell
git remote add origin https://github.com/VibeCoder01/VOP.git
git fetch origin
git checkout -b codex/phase-0 origin/main
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-offline.txt
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe tools\generate_fixture.py
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m vop demo --image fixtures\scene.png --engine mock
.\.venv\Scripts\python.exe -m vop check-env
.\.venv\Scripts\python.exe -m vop benchmark --engine liquid-d1-3b --image fixtures\scene.png --reference-dell --output-dir reports\local
git diff --check
```

Installation, fixture generation, mock demo and inventory succeeded on Windows 11 Pro build
26300, Python 3.11.9. `pip check`: no broken requirements. The initial test run had 76 passes
and one test failure caused by demanding strictly different timestamps for an instant mock
call. Windows clock resolution permits equality; the assertion was corrected. Subsequent
runs passed, including the added internal worker consent test: **78 passed**. The most recent
local run after report-format changes took 1.12 s. `git diff --check` found no whitespace errors (Git emitted its normal
LF-to-CRLF notice). Tests deny socket connections; no weights, cameras or credentials required.

The declined-consent benchmark wrote both reports with `not_run`, null measurements and
exit code 2, as documented. The shell session wrapper reported a nonzero final command;
this is expected for a benchmark that did not run, not a failed offline test. Local optional
model dependencies were not installed and no weights downloaded to the laptop.

Read-only model API metadata and source files were fetched to inspect schema and resolve
the SHA. `pip index versions` confirmed candidate direct package versions. `gh auth status`
could not run because `gh` is not installed; Git/GitHub connector tooling handles delivery.

## Alternate host execution

After explicit product-owner authorisation, the same source/test/fixture package was copied
to an isolated temporary directory on a separately provisioned Linux AI machine. No server
network address, credentials or private configuration is committed. The remote system is
Python 3.14.4 / i7-12700KF / 65,854,894,080 physical RAM bytes. The following host-local
commands were executed, with `$run` denoting the private temporary directory:

```sh
python3 -m zipfile -e "$run/source.zip" "$run/source"
python3 -m venv --without-pip "$run/venv"
python3 -m pip --python "$run/venv/bin/python" install pip==26.2.1 -r "$run/source/requirements-offline.txt"
"$run/venv/bin/python" -m pip install torch==2.14.1 torchvision==0.29.1 --index-url https://download.pytorch.org/whl/cpu
"$run/venv/bin/python" -m pip install transformers==5.19.0
"$run/venv/bin/python" -m pip install --no-deps --no-build-isolation -e "$run/source"
"$run/venv/bin/python" -m pip check
cd "$run/source"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$run/venv/bin/python" -m pytest -q
"$run/venv/bin/python" -m vop check-env
"$run/venv/bin/python" -m vop benchmark --image fixtures/scene.png --allow-model-download --accept-model-risk --cache-dir "$run/model-cache" --output-dir "$run/reports" --timeout-seconds 900 --repeats 3
"$run/venv/bin/python" -m pip freeze --exclude-editable
```

The usual `python3 -m venv` initially failed because system Python lacked ensurepip. The
documented pip `--python` mechanism populated a `--without-pip` venv without altering system
Python. Initial Windows `scp` attempts failed because its matching ssh binary was absent;
the existing Git OpenSSH tools transferred the archive successfully. The isolated runtime
installation and `pip check` succeeded. **78 offline tests passed in 0.38 s** on Linux/Python
3.14.4. CPU package versions: Torch 2.14.1+cpu, torchvision 0.29.1+cpu, Transformers 5.19.0,
huggingface-hub 2.2.0. Full installed closure is in `requirements-liquid-linux-cpu.lock.txt`.
The real benchmark **passed** all 12 calls. Warm median latencies for 1/3/5 questions were
6.745/9.437/11.307 s, with sampled peak process-tree RSS 19,005,329,408 bytes (17.700 GiB),
minimum available RAM 28,753,559,552 bytes, and sampled process-tree swap 344,375,296 bytes
(328.422 MiB, below the 512 MiB failure threshold). Download/cache resolution took 125.336 s;
the model-load stage took 1.294 s, excluding later lazy processor/runtime setup. Actual
outputs correctly represented the synthetic red square, blue circle, white background,
absent green triangle and ordinal brightness; this is a single fixture, not general accuracy
validation. Full first/warm samples and native output are in `alternate-server/phase0-report.json`.
Only the ephemeral absolute cache directory is redacted in the shareable report; the original
is retained locally in ignored `.cache/`. No private server address or user configuration is saved.

A separate bounded load-only check used the same adapter/cache and confirmed actual model
dtype `torch.float32`, CPU device, 3,123,483,888 parameters and exclusively FP32 floating
parameters. It ran as `timeout 60 "$run/venv/bin/python" "$run/verify_runtime.py" "$run/model-cache"`.
The script loaded with both explicit consent flags, inspected `model.dtype`, `model.device`,
`sum(p.numel() for p in model.parameters())`, and the floating-parameter dtype set, then asserted
FP32/CPU. No further inference benchmark was run. Original raw output fields are retained.

The owner explicitly accepted the alternate CPU feasibility result and made Dell feasibility
nonblocking. Offline results never stand in for actual model output. The isolated environment
and pinned weights remain on the authorised server in its temporary run directory; no service
or system-Python modification was installed. GPU inference has not been attempted.

## Acceptance criteria

| ID | Result | Evidence / limit |
|---|---|---|
| P0-01 | PASS | Fresh venv, pinned offline closure, editable install and tests on Windows; exact README commands. |
| P0-02 | PASS | Synthetic PNG and exit-0 mock demo, three questions on a common frame, explicit mock label. |
| P0-03 | PASS | Binary/choice/ordinal mapping, malformed/unsupported native outputs, preserved fields, two interchangeable engines, byte-only request boundary. |
| P0-04 | PASS | Missing/corrupt/unsupported images, exceptions, OOM and timeouts typed; failed values remain null. |
| P0-05 | PASS | Two consent flags, approved SHA only, memory/disk preflight, local override, isolated timeout/memory watchdog; no CI model install/download. |
| P0-06 | PASS | JSON/Markdown report with actual Dell inventory, requested candidate SHA, not-run reason and null measurements; alternate run separated. |
| P0-07 | PASS | PowerShell setup/benchmark instructions, expected outputs, limits, licence separation and recommendation. |
| P0-08 | LOCAL PASS; CI pending | 78 offline tests passed on Windows 3.11 and Linux 3.14; Actions matrix result must be checked after push. |
| P0-09 | DELL NOT RUN; ALTERNATE CPU PASS | Actual official FP32/CPU outputs for 1/3/5 questions on alternate host, accepted by owner as sufficient; Dell result remains unknown. |
| P0-10 | GO | ADR-0003; proceed to Phase 1 foundation review using sparse server CPU inference, with routine later accuracy/capacity/licence decisions open. |

## Changed files and boundaries

Added `pyproject.toml`, dependency pins/recorded Linux CPU lock, `.gitignore`, `src/vop/`
(contracts, file input, mock/Liquid engines, CLI, inventory, benchmark and example questions),
`tests/` (offline network denial plus contract/adapter/mock/native/error/benchmark coverage),
synthetic `fixtures/scene.png`, fixture generator, Actions Windows/Ubuntu workflow,
feasibility/validation reports and ADR-0003. Updated README/CHANGELOG and only the stale
SRS version comment in `plugin-contracts.yaml`. Existing SRS, handoff contract and ADRs retained.

No model weights, live imagery, credentials, private endpoints, dashboard, database,
camera/remote worker service or licence selection added. Benchmarks are not accuracy tests.
Sampled RSS can miss peaks; Windows pagefile stress is not directly observable by this
watchdog. Linux per-process swap is sampled and >512 MiB triggers failed_oom. Only the
benchmark has a hard interruptible deadline. Optional Windows model compatibility is open.

**Recommendation: GO** under the owner's accepted alternate CPU criterion. The tested d1-3B
runtime is a viable Phase 1 engine candidate for sparse still images on the server; it is not
a GPU, real-time or production-accuracy claim. Phase 1 remains explicitly unauthorised.
