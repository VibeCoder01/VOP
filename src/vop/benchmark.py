"""Explicit opt-in benchmark, isolated from the CLI and bounded by a parent watchdog."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from time import monotonic, sleep

import psutil

from vop.contracts import InferenceRequest, ProviderError, Status, infer, json_default, utcnow
from vop.environment import inventory, versions
from vop.examples import questions
from vop.inference.liquid_d1 import CHECKPOINT_REVISION, MODEL_ID, LiquidD1InferenceAdapter
from vop.inputs.file_image import FileImageAdapter

GIB = 1024 ** 3
OUTCOMES = {"not_run", "blocked_preflight", "passed", "failed_oom", "failed_dependency",
            "failed_runtime", "failed_timeout"}
WARNING = ("WARNING: official d1-3B executes checkpoint Python code and downloads several GB. "
           "FP32 weights alone are about 12.5 GB (estimate, not a measurement); loading and "
           "inference need additional memory and may exhaust a 16 GB machine. No threshold guarantees safety.")


def write_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, default=json_default, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_reports(report: dict, output_dir: str | Path) -> None:
    assert report["outcome"] in OUTCOMES
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "phase0-report.json", report)
    text = (f"# Phase 0 feasibility report\n\nOutcome: **{report['outcome']}**\n\n"
            f"Reason: {report['reason']}\n\nTarget: {report['benchmark_target']}\n\n"
            "Missing measurements are null. Synthetic mock answers are never benchmark data.\n\n"
            "## Measured timings\n\n"
            "| Questions | First call (ms) | Warm samples | Warm median (ms) | Warm max (ms) | p95 (ms) |\n"
            "|---|---|---|---|---|---|\n")
    for case in report["cases"]:
        fields = ("question_count", "first_call_ms", "warm_sample_count", "warm_median_ms", "warm_max_ms", "warm_p95_ms")
        text += "| " + " | ".join(str(case[k]) if case[k] is not None else "null" for k in fields) + " |\n"
    if not report["cases"]:
        text += "\nNo inference calls ran; latency and sample counts are unmeasured.\n"
    text += "\n## Environment, provenance and resource measurements\n\n```json\n"
    text += json.dumps({k: v for k, v in report.items() if k not in ("cases", "worker_log_tail")},
                       indent=2, default=json_default, allow_nan=False) + "\n```\n"
    for case in report["cases"]:
        if case["outputs"]:
            text += f"\n## Actual first-call native output: {case['question_count']} questions\n\n```json\n"
            text += json.dumps(case["outputs"][0]["provider_raw"], indent=2, default=json_default,
                               allow_nan=False) + "\n```\n"
    text += "\nThe companion JSON retains every call's actual native and normalised output.\n"
    (output / "phase0-report.md").write_text(text, encoding="utf-8")


def base_report(environment: dict, target: str) -> dict:
    return {"schema_version": 1, "created_at_utc": utcnow().isoformat(), "benchmark_target": target,
            "outcome": "not_run", "reason": "Operator has not consented to model download and execution",
            "environment": environment, "model": {"id": MODEL_ID, "requested_revision": CHECKPOINT_REVISION,
            "resolved_revision": None, "revision_validation": "source/API inspected; runtime unvalidated",
            "cache_path": None, "weight_blob_hashes": None, "dtype": "float32", "device": "cpu"},
            "image": None, "model_load_ms": None, "download_ms": None, "peak_process_tree_rss_bytes": None,
            "minimum_available_physical_bytes": None, "sampling_interval_seconds": 0.1,
            "peak_process_tree_swap_bytes": None,
            "swap_measurement": "Linux per-process swap when readable; unavailable on Windows",
            "memory_measurement": "sampled RSS/working set; can miss transient peaks; no pagefile guarantee",
            "cases": [], "operator_consent": False, "preflight_override": False,
            "recommendation": "CONDITIONAL GO: offline architecture; real inference feasibility remains unresolved"}


def preflight(environment: dict) -> list[str]:
    issues = []
    if environment["available_physical_bytes"] < 16 * GIB:
        issues.append("Available physical RAM is below the conservative 16 GiB experiment threshold")
    if environment["free_disk_bytes"] < 20 * GIB:
        issues.append("Free cache disk space is below the conservative 20 GiB threshold")
    if environment["architecture"].lower() not in ("amd64", "x86_64", "arm64", "aarch64"):
        issues.append("A 64-bit runtime is required")
    return issues


def terminate_tree(proc: subprocess.Popen) -> None:
    try:
        root = psutil.Process(proc.pid)
        children = root.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        root.kill()
        psutil.wait_procs(children, timeout=5)
    except psutil.NoSuchProcess:
        pass
    finally:
        proc.wait(timeout=10)


def run_benchmark(args: argparse.Namespace) -> dict:
    environment = inventory(args.cache_dir)
    report = base_report(environment, "reference_dell" if args.reference_dell else "execution_host (not a Dell claim)")
    report["preflight_issues"] = preflight(environment)
    report["timeout_seconds"] = args.timeout_seconds
    if not args.allow_model_download or not args.accept_model_risk:
        write_reports(report, args.output_dir)
        return report
    report["operator_consent"] = True
    report["preflight_override"] = args.override_preflight
    hw = environment["hardware"]
    if args.reference_dell and not (environment["windows_build"] and "Dell" in (hw["manufacturer"] or "")
                                    and "i5-10310U" in hw["cpu"] and 15 * GIB <= environment["total_physical_bytes"] <= 17 * GIB):
        report.update(outcome="blocked_preflight", reason="Execution machine does not match the reference Dell")
    elif report["preflight_issues"] and not args.override_preflight:
        report.update(outcome="blocked_preflight", reason="; ".join(report["preflight_issues"]))
    elif environment["available_physical_bytes"] <= 2 * GIB:
        report.update(outcome="blocked_preflight", reason="Cannot preserve the non-overridable 2 GiB RAM reserve")
    elif any(environment["dependencies"].get(name) is None for name in ("torch", "torchvision", "transformers", "huggingface-hub")):
        report.update(outcome="failed_dependency", reason="Install the separate optional model dependencies first")
    else:
        try:
            frame = FileImageAdapter().read(args.image)
            report["image"] = {"sha256": frame.sha256, "width": frame.width, "height": frame.height,
                               "capture_time_semantics": "file import instant; original capture time unknown"}
        except ProviderError as exc:
            report.update(outcome="failed_runtime", reason=str(exc))
            write_reports(report, args.output_dir)
            return report
        with tempfile.TemporaryDirectory(prefix="vop-benchmark-") as temporary:
            root = Path(temporary)
            config = {"image": str(Path(args.image).resolve()), "cache_dir": str(Path(args.cache_dir).resolve()),
                      "repeats": args.repeats, "allow_model_download": True, "accept_model_risk": True}
            write_json(root / "config.json", config)
            started = monotonic()
            rss_peak = 0
            swap_peak = None
            min_available = environment["available_physical_bytes"]
            forced = None
            try:
                with (root / "worker.log").open("w", encoding="utf-8") as log:
                    proc = subprocess.Popen([sys.executable, "-m", "vop.benchmark", "--worker",
                                             str(root / "config.json"), "--result", str(root / "result.json")],
                                            stdout=log, stderr=log)
                    while proc.poll() is None:
                        try:
                            process = psutil.Process(proc.pid)
                            processes = [process, *process.children(recursive=True)]
                            rss = sum(p.memory_info().rss for p in processes)
                            rss_peak = max(rss_peak, rss)
                            if sys.platform.startswith("linux"):
                                swapped = sum(p.memory_full_info().swap for p in processes)
                                swap_peak = max(swap_peak or 0, swapped)
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        available = psutil.virtual_memory().available
                        min_available = min(min_available, available)
                        if monotonic() - started >= args.timeout_seconds:
                            forced = ("failed_timeout", "Child process exceeded total download/load/inference timeout")
                        elif available < 2 * GIB or rss_peak > environment["available_physical_bytes"] - 2 * GIB:
                            forced = ("failed_oom", "RAM watchdog stopped the child to preserve the 2 GiB reserve")
                        elif swap_peak is not None and swap_peak > GIB / 2:
                            forced = ("failed_oom", "Child process-tree swap exceeded 512 MiB; pagefile stress is not a pass")
                        if forced:
                            terminate_tree(proc)
                            break
                        sleep(0.1)
                    if (root / "result.json").exists():
                        report.update(json.loads((root / "result.json").read_text(encoding="utf-8")))
                    else:
                        report.update(outcome="failed_runtime", reason=f"Child exited without results (exit {proc.returncode})")
                    if forced:
                        report.update(outcome=forced[0], reason=forced[1])
                    elif proc.returncode != 0 and report["outcome"] == "passed":
                        report.update(outcome="failed_runtime", reason=f"Child exited with code {proc.returncode}")
                    report["worker_log_tail"] = (root / "worker.log").read_text(encoding="utf-8", errors="replace")[-4000:]
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                report.update(outcome="failed_runtime", reason=f"{type(exc).__name__}: {exc}")
            finally:
                if "proc" in locals() and proc.poll() is None:
                    terminate_tree(proc)
            report["peak_process_tree_rss_bytes"] = rss_peak or None
            report["minimum_available_physical_bytes"] = min_available
            report["peak_process_tree_swap_bytes"] = swap_peak
    if report["outcome"] != "passed":
        report["recommendation"] = "CONDITIONAL GO: architecture viable; select a real engine after hardware/compatibility validation"
    else:
        report["recommendation"] = "CONDITIONAL GO: review measured latency and accuracy before selecting the Phase 1 engine"
    write_reports(report, args.output_dir)
    return report


def worker(config_path: Path, output_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    data = {"outcome": "failed_runtime", "reason": "Worker started; model not yet loaded", "cases": [],
            "model_load_ms": None, "worker_dependencies": versions()}
    write_json(output_path, data)
    engine = LiquidD1InferenceAdapter()
    try:
        if not config.get("allow_model_download") or not config.get("accept_model_risk"):
            data.update(outcome="not_run", reason="Worker config lacks explicit download and execution consent")
            write_json(output_path, data)
            return
        engine.load(allow_model_download=True, accept_model_risk=True, cache_dir=config["cache_dir"])
        data["model_load_ms"] = engine.model_load_ms
        data["download_ms"] = engine.download_ms
        snapshot = Path(engine.snapshot_path)
        data["model"] = {"id": MODEL_ID, "requested_revision": CHECKPOINT_REVISION,
                         "resolved_revision": snapshot.name, "cache_path": str(snapshot),
                         "revision_validation": "loaded; system_one validation pending", "dtype": "float32", "device": "cpu",
                         "weight_blob_hashes": {p.name: p.resolve().name for p in snapshot.glob("*.safetensors")
                                                if len(p.resolve().name) == 64}}
        write_json(output_path, data)
        frame = FileImageAdapter().read(config["image"])
        for count in (1, 3, 5):
            case = {"question_count": count, "first_call_ms": None, "warm_sample_count": 0,
                    "warm_latencies_ms": [], "warm_median_ms": None, "warm_max_ms": None,
                    "warm_p95_ms": None, "outputs": []}
            data["cases"].append(case)
            request = InferenceRequest(frame, questions()[:count])
            for repetition in range(config["repeats"] + 1):
                started = monotonic()
                answer = infer(engine, request)
                elapsed = (monotonic() - started) * 1000
                case["outputs"].append(asdict(answer))
                if repetition == 0:
                    case["first_call_ms"] = elapsed
                else:
                    case["warm_latencies_ms"].append(elapsed)
                    case["warm_sample_count"] += 1
                    case["warm_median_ms"] = statistics.median(case["warm_latencies_ms"])
                    case["warm_max_ms"] = max(case["warm_latencies_ms"])
                write_json(output_path, data)
                if answer.status != Status.SUCCESS:
                    error = answer.error or next((a.error for a in answer.answers if a.error), None)
                    raise error or ProviderError("invalid_result", "Provider output did not validate")
            if case["warm_sample_count"] >= 20:
                case["warm_p95_ms"] = statistics.quantiles(case["warm_latencies_ms"], n=100, method="inclusive")[94]
        data["model"]["revision_validation"] = "system_one validated on recorded benchmark image; no accuracy claim"
        data.update(outcome="passed", reason="All 1/3/5-question calls returned valid native output")
    except Exception as exc:
        message = str(exc)
        if isinstance(exc, (ImportError, ModuleNotFoundError)) or isinstance(exc, ProviderError) and exc.code == "dependency_missing":
            outcome = "failed_dependency"
        elif (isinstance(exc, MemoryError) or isinstance(exc, ProviderError) and exc.code == "inference_oom"
              or any(token in message.lower() for token in ("out of memory", "cannot allocate memory", "not enough memory", "bad allocation"))):
            outcome = "failed_oom"
        elif isinstance(exc, TimeoutError) or isinstance(exc, ProviderError) and exc.status == Status.TIMEOUT:
            outcome = "failed_timeout"
        else:
            outcome = "failed_runtime"
        data.update(outcome=outcome, reason=f"{type(exc).__name__}: {message}")
        if getattr(engine, "snapshot_path", None):
            data["model"] = {"id": MODEL_ID, "requested_revision": CHECKPOINT_REVISION,
                             "resolved_revision": Path(engine.snapshot_path).name, "cache_path": engine.snapshot_path,
                             "revision_validation": "downloaded; runtime failed validation", "dtype": "float32", "device": "cpu",
                             "weight_blob_hashes": None}
        data["model_load_ms"] = getattr(engine, "model_load_ms", None)
        data["download_ms"] = getattr(engine, "download_ms", None)
    write_json(output_path, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    cli = parser.parse_args()
    worker(cli.worker, cli.result)
