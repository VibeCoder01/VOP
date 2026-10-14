"""Bounded actual HTTP overload soak against a disposable synthetic worker. No weights/cameras."""
import argparse
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
from threading import Event, Lock, Thread
from time import monotonic, sleep
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from uuid import uuid4

import psutil
from process_cleanup import stop_process
from vop.contracts import InferenceRequest, utcnow
from vop.examples import questions
from vop.inputs.file_image import FileImageAdapter
from vop.worker_protocol import encode, request_body


def main():
    parser = argparse.ArgumentParser(description="Explicit synthetic overload soak")
    parser.add_argument("--seconds", type=float, default=3600)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 7200:
        parser.error("Duration must be 1–7200 seconds")
    root = Path(__file__).resolve().parents[1]
    token = secrets.token_urlsafe(32)
    counters = {"success": 0, "overloaded": 0, "errors": 0}
    lock, stop = Lock(), Event()
    report = {"result": "running", "duration_requested_seconds": args.seconds, "input": "synthetic", "peak_worker_tree_rss_bytes": 0, "max_observed_queue_depth": 0, "health_failures": 0}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vop-phase4-soak-") as folder:
        secret_file = Path(folder) / "worker.token"
        secret_file.write_text(token, encoding="utf-8")
        secret_file.chmod(0o600)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        process = subprocess.Popen([sys.executable, str(root/"tools/run_worker.py"), "--worker-id", "soak-worker", "--port", str(port), "--token-file", str(secret_file), "--backend", "mock", "--mock-delay-seconds", ".05"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        def health():
            with urlopen(Request(base+"/health", headers=headers), timeout=2) as response:
                return json.load(response)
        try:
            for _ in range(200):
                try:
                    if health()["ready"]: break
                except (URLError, OSError):
                    if process.poll() is not None: raise RuntimeError("Worker failed to start")
                sleep(.05)
            else: raise RuntimeError("Worker startup deadline")
            frame = FileImageAdapter().read(root/"fixtures/scene.png")
            def load():
                while not stop.is_set():
                    item = replace(frame, frame_id=str(uuid4()), captured_at_utc=utcnow(), received_at_utc=utcnow())
                    body = request_body(InferenceRequest(item, questions()[:1], utcnow()+timedelta(seconds=2)), "soak-worker")
                    key = "errors"
                    try:
                        with urlopen(Request(base+"/infer", data=encode(body), headers=headers), timeout=3) as response:
                            value = json.load(response)
                            key = "success" if value["result"]["status"] == "success" else "errors"
                    except HTTPError as exc:
                        key = "overloaded" if exc.code == 429 else "errors"
                    except Exception: pass
                    with lock: counters[key] += 1
                    stop.wait(.1)
            threads = [Thread(target=load, daemon=True) for _ in range(6)]
            for thread in threads: thread.start()
            started = monotonic()
            sampled = psutil.Process(process.pid)
            next_progress = started + 60
            while monotonic()-started < args.seconds:
                if psutil.virtual_memory().available < 2*1024**3:
                    raise RuntimeError("Host RAM reserve guard")
                rss = sum(p.memory_info().rss for p in [sampled, *sampled.children(recursive=True)] if p.is_running())
                report["peak_worker_tree_rss_bytes"] = max(report["peak_worker_tree_rss_bytes"], rss)
                try:
                    status = health()
                    report["max_observed_queue_depth"] = max(report["max_observed_queue_depth"], status["queue_depth"])
                    report["worker_reported_skips"] = status["skipped"]
                except Exception: report["health_failures"] += 1
                if monotonic() >= next_progress:
                    print(json.dumps({"elapsed_seconds": round(monotonic()-started), **counters}), flush=True)
                    next_progress += 60
                stop.wait(min(1, args.seconds-(monotonic()-started)))
            stop.set()
            for thread in threads: thread.join(timeout=4)
            report.update(duration_actual_seconds=monotonic()-started, **counters)
            report["result"] = "PASS" if counters["success"] and counters["overloaded"] and not counters["errors"] and not report["health_failures"] and report["max_observed_queue_depth"] == 0 else "FAIL"
        except Exception as exc:
            report.update(result="FAIL", reason=str(exc))
        finally:
            stop.set()
            stop_process(process)
            args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
        return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
