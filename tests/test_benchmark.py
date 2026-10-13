import argparse
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from vop import benchmark
from vop.__main__ import main
from vop.contracts import ProviderError, Status
from vop.examples import MOCK_ANSWERS
from vop.inference.mock import MockInferenceEngine


def environment(memory=32 * benchmark.GIB):
    return {"available_physical_bytes": memory, "total_physical_bytes": 16 * benchmark.GIB,
            "free_disk_bytes": 40 * benchmark.GIB, "architecture": "AMD64", "windows_build": "10.0.26100",
            "hardware": {"cpu": "Intel i5-10310U", "manufacturer": "Dell Inc."},
            "dependencies": dict.fromkeys(("torch", "torchvision", "transformers", "huggingface-hub"), "test")}


def args(tmp_path, **overrides):
    options = dict(image=str(Path(__file__).resolve().parents[1] / "fixtures" / "scene.png"),
                   allow_model_download=False, accept_model_risk=False, override_preflight=False,
                   reference_dell=False, cache_dir=str(tmp_path / "cache"), output_dir=str(tmp_path / "reports"),
                   timeout_seconds=0.2, repeats=3)
    options.update(overrides)
    return argparse.Namespace(**options)


def no_child(*args, **kwargs):
    raise AssertionError("Model child must not launch")


@pytest.mark.parametrize("download,risk", [(False, False), (True, False), (False, True)])
def test_declined_consent_never_launches(monkeypatch, tmp_path, download, risk):
    monkeypatch.setattr(benchmark, "inventory", lambda path: environment())
    monkeypatch.setattr(benchmark.subprocess, "Popen", no_child)
    report = benchmark.run_benchmark(args(tmp_path, allow_model_download=download, accept_model_risk=risk))
    assert report["outcome"] == "not_run" and report["model_load_ms"] is None
    assert report["model"]["resolved_revision"] is None
    assert json.loads((tmp_path / "reports" / "phase0-report.json").read_text())["cases"] == []
    assert "not_run" in (tmp_path / "reports" / "phase0-report.md").read_text()


def test_low_memory_blocks_without_override(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "inventory", lambda path: environment(6 * benchmark.GIB))
    monkeypatch.setattr(benchmark.subprocess, "Popen", no_child)
    report = benchmark.run_benchmark(args(tmp_path, allow_model_download=True, accept_model_risk=True))
    assert report["outcome"] == "blocked_preflight" and report["peak_process_tree_rss_bytes"] is None


def test_disk_preflight_and_no_guarantee():
    env = environment()
    env["free_disk_bytes"] = benchmark.GIB
    assert any("disk" in text for text in benchmark.preflight(env))


def test_missing_dependency_recorded_without_download(monkeypatch, tmp_path):
    env = environment()
    env["dependencies"]["torch"] = None
    monkeypatch.setattr(benchmark, "inventory", lambda path: env)
    monkeypatch.setattr(benchmark.subprocess, "Popen", no_child)
    report = benchmark.run_benchmark(args(tmp_path, allow_model_download=True, accept_model_risk=True))
    assert report["outcome"] == "failed_dependency"


def test_reference_host_cannot_be_substituted(monkeypatch, tmp_path):
    env = environment()
    env["hardware"]["manufacturer"] = "Other"
    monkeypatch.setattr(benchmark, "inventory", lambda path: env)
    monkeypatch.setattr(benchmark.subprocess, "Popen", no_child)
    report = benchmark.run_benchmark(args(tmp_path, allow_model_download=True, accept_model_risk=True, reference_dell=True))
    assert report["outcome"] == "blocked_preflight" and "reference Dell" in report["reason"]


def test_hard_timeout_kills_real_child_without_model(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "inventory", lambda path: environment())
    real_popen = subprocess.Popen
    children = []
    def sleeper(command, **kwargs):
        proc = real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        children.append(proc)
        return proc
    monkeypatch.setattr(benchmark.subprocess, "Popen", sleeper)
    report = benchmark.run_benchmark(args(tmp_path, allow_model_download=True, accept_model_risk=True))
    assert report["outcome"] == "failed_timeout"
    assert children[0].poll() is not None
    assert report["peak_process_tree_rss_bytes"] > 0
    assert report["model_load_ms"] is None


def test_memory_watchdog_stops_child(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "inventory", lambda path: environment())
    monkeypatch.setattr(benchmark.psutil, "virtual_memory", lambda: SimpleNamespace(available=benchmark.GIB))
    real_popen = subprocess.Popen
    monkeypatch.setattr(benchmark.subprocess, "Popen", lambda command, **kwargs:
                        real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs))
    report = benchmark.run_benchmark(args(tmp_path, allow_model_download=True, accept_model_risk=True))
    assert report["outcome"] == "failed_oom"


def test_worker_question_counts_repeats_and_output_preservation(monkeypatch, tmp_path):
    calls = []
    class FakeLiquid(MockInferenceEngine):
        snapshot_path = str(tmp_path / benchmark.CHECKPOINT_REVISION)
        model_load_ms = 1.0
        download_ms = 2.0
        def __init__(self):
            super().__init__(MOCK_ANSWERS)
        def load(self, **kwargs):
            calls.append(kwargs)
    monkeypatch.setattr(benchmark, "LiquidD1InferenceAdapter", FakeLiquid)
    config = tmp_path / "config.json"
    benchmark.write_json(config, {"image": args(tmp_path).image, "cache_dir": str(tmp_path), "repeats": 3,
                                  "allow_model_download": True, "accept_model_risk": True})
    output = tmp_path / "result.json"
    benchmark.worker(config, output)
    data = json.loads(output.read_text())
    assert data["outcome"] == "passed"
    assert [c["question_count"] for c in data["cases"]] == [1, 3, 5]
    assert all(c["warm_sample_count"] == 3 and len(c["outputs"]) == 4 for c in data["cases"])
    assert all(c["first_call_ms"] is not None and c["warm_p95_ms"] is None for c in data["cases"])
    assert len({o["frame_id"] for c in data["cases"] for o in c["outputs"]}) == 1
    assert calls[0]["allow_model_download"] and calls[0]["accept_model_risk"]


@pytest.mark.parametrize("error,outcome", [(MemoryError("OOM"), "failed_oom"),
                                          (ImportError("missing"), "failed_dependency"),
                                          (TimeoutError("late"), "failed_timeout"),
                                          (RuntimeError("broken"), "failed_runtime")])
def test_worker_failure_taxonomy(monkeypatch, tmp_path, error, outcome):
    class Broken:
        def load(self, **kwargs):
            raise error
    monkeypatch.setattr(benchmark, "LiquidD1InferenceAdapter", Broken)
    config = tmp_path / "config.json"
    benchmark.write_json(config, {"cache_dir": str(tmp_path), "allow_model_download": True, "accept_model_risk": True})
    benchmark.worker(config, tmp_path / "result.json")
    data = json.loads((tmp_path / "result.json").read_text())
    assert data["outcome"] == outcome and data["model_load_ms"] is None


def test_internal_worker_cannot_bypass_consent(monkeypatch, tmp_path):
    class Forbidden:
        def load(self, **kwargs):
            raise AssertionError("Consent must be checked first")
    monkeypatch.setattr(benchmark, "LiquidD1InferenceAdapter", Forbidden)
    config = tmp_path / "config.json"
    benchmark.write_json(config, {})
    benchmark.worker(config, tmp_path / "result.json")
    assert json.loads((tmp_path / "result.json").read_text())["outcome"] == "not_run"


def test_demo_cli_mock_only(capsys):
    code = main(["demo", "--image", args(Path(".")).image])
    output = json.loads(capsys.readouterr().out)
    assert code == 0 and output["synthetic"] and len(output["answers"]) == 3


def test_cli_bad_image_failure(capsys, tmp_path):
    assert main(["demo", "--image", str(tmp_path / "missing.png")]) == 1
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "image_missing"


def test_default_cli_benchmark_no_consent(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(benchmark, "inventory", lambda path: environment())
    monkeypatch.setattr(benchmark.subprocess, "Popen", no_child)
    assert main(["benchmark", "--image", args(tmp_path).image, "--output-dir", str(tmp_path)]) == 2
    output = capsys.readouterr()
    assert "WARNING" in output.err and json.loads(output.out)["outcome"] == "not_run"


@pytest.mark.parametrize("option,value", [("--timeout-seconds", "nan"), ("--timeout-seconds", "0"), ("--repeats", "2")])
def test_benchmark_bounds(option, value):
    with pytest.raises(SystemExit):
        main(["benchmark", "--image", "unused.png", option, value])
