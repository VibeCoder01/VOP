"""Opt-in isolated GPU fixture benchmark; writes factual results, never stores camera images."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import threading
from time import perf_counter

from vop.contracts import InferenceRequest, Status, infer, json_default
from vop.examples import questions
from vop.inference.liquid_d1 import CHECKPOINT_REVISION, LiquidD1InferenceAdapter
from vop.inputs.file_image import FileImageAdapter


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--precision", choices=("float32", "bfloat16", "float16"), default="bfloat16")
    parser.add_argument("--accept-model-risk", action="store_true", required=True)
    args = parser.parse_args()
    import psutil
    import torch
    from importlib.metadata import version
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "model_revision": CHECKPOINT_REVISION,
              "device_requested": "cuda:0", "precision": args.precision, "torch": torch.__version__, "cuda": torch.version.cuda,
              "accelerate": version("accelerate"), "transformers": version("transformers"),
              "outcome": "not_run", "cases": [], "peak_host_rss_bytes": 0, "peak_child_swap_bytes": 0}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, default=json_default, indent=2, allow_nan=False), encoding="utf-8")
    stopped = threading.Event()
    def watchdog():
        process = psutil.Process()
        while not stopped.wait(.2):
            report["peak_host_rss_bytes"] = max(report["peak_host_rss_bytes"], process.memory_info().rss)
            report["peak_child_swap_bytes"] = max(report["peak_child_swap_bytes"], getattr(process.memory_full_info(), "swap", 0))
            if psutil.virtual_memory().available < 2 * 1024**3 or report["peak_child_swap_bytes"] > 512 * 1024**2:
                report.update(outcome="aborted_resource_guard")
                save()
                os._exit(2)
    monitor = threading.Thread(target=watchdog, daemon=True)
    monitor.start()
    try:
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable")
        report["gpu_name"] = torch.cuda.get_device_name(0)
        report["gpu_capability"] = torch.cuda.get_device_capability(0)
        report["free_vram_before_bytes"], report["total_vram_bytes"] = torch.cuda.mem_get_info()
        if report["free_vram_before_bytes"] < 12 * 1024**3:
            raise RuntimeError("Less than conservative 12 GiB free GPU memory")
        torch.cuda.reset_peak_memory_stats()
        engine = LiquidD1InferenceAdapter(device="cuda:0", precision=args.precision)
        start = perf_counter()
        engine.load(allow_model_download=True, accept_model_risk=args.accept_model_risk, cache_dir=args.cache_dir)
        torch.cuda.synchronize()
        report["load_seconds"] = perf_counter() - start
        report["parameter_devices"] = sorted({str(p.device) for p in engine.model.parameters()})
        report["floating_parameter_dtypes"] = sorted({str(p.dtype) for p in engine.model.parameters() if p.is_floating_point()})
        if report["parameter_devices"] != ["cuda:0"]:
            raise RuntimeError("Parameters were not all placed on CUDA")
        frame = FileImageAdapter().read(Path(__file__).resolve().parents[1] / "fixtures/scene.png")
        for count in (1, 3, 5):
            runs = []
            for repetition in range(4):
                torch.cuda.synchronize()
                start = perf_counter()
                result = infer(engine, InferenceRequest(frame, questions()[:count]))
                torch.cuda.synchronize()
                elapsed = perf_counter() - start
                runs.append({"seconds": elapsed, "result": asdict(result)})
                if result.status != Status.SUCCESS:
                    report["cases"].append({"questions": count, "runs": runs})
                    raise RuntimeError("GPU inference returned typed failure")
            report["cases"].append({"questions": count, "first_seconds": runs[0]["seconds"],
                                    "warm_median_seconds": statistics.median(r["seconds"] for r in runs[1:]), "runs": runs})
            save()
        report.update(outcome="passed", peak_vram_allocated_bytes=torch.cuda.max_memory_allocated(), peak_vram_reserved_bytes=torch.cuda.max_memory_reserved())
    except Exception as exc:
        report.update(outcome="failed", reason=f"{type(exc).__name__}: {str(exc)[:500]}")
    finally:
        stopped.set()
        monitor.join(timeout=1)
        save()
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}))
    return 0 if report["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
