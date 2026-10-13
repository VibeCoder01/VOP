"""Loopback HTTP smoke on Windows/Linux; token and DB exist only for this run."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="vop-phase1-smoke-") as directory:
    work = Path(directory)
    config = json.loads((root / "sample-config" / "phase1.json").read_text(encoding="utf-8"))
    config["database"] = "smoke.sqlite3"
    path = work / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = secrets.token_urlsafe(32)
    environment = {**os.environ, "VOP_API_TOKEN": token}
    base = f"http://127.0.0.1:{port}"
    def call(route, *, method="GET", body=None, headers=None):
        req = Request(base + route, data=body, method=method, headers={"Authorization": "Bearer " + token, **(headers or {})})
        with urlopen(req, timeout=5) as response:
            return response.status, json.load(response)
    def start():
        proc = subprocess.Popen([sys.executable, "-m", "vop", "serve", "--config", str(path), "--port", str(port)],
                                cwd=root, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for attempt in range(100):
            try:
                call("/api/v1/health")
                return proc
            except (URLError, OSError):
                if proc.poll() is not None:
                    raise RuntimeError("Service exited during startup")
                time.sleep(0.05)
        proc.terminate()
        proc.wait(timeout=5)
        raise RuntimeError("Service startup timed out")
    proc = start()
    try:
        status, run = call("/api/v1/sources/synthetic-scene/capture", method="POST")
        assert status == 201 and run["result"]["synthetic"] and len(run["result"]["answers"]) == 3
        status, rows = call("/api/v1/observations")
        assert status == 200 and len(rows["observations"]) == 3
        try:
            urlopen(base + "/api/v1/health", timeout=5)
            raise AssertionError("Unauthenticated request succeeded")
        except HTTPError as exc:
            assert exc.code == 401
        payload = (root / "fixtures" / "scene.png").read_bytes()
        headers = {"Content-Type": "image/png", "X-Frame-ID": "smoke-frame"}
        first_status, first = call("/api/v1/sources/synthetic-scene/frames", method="POST", body=payload, headers=headers)
        second_status, second = call("/api/v1/sources/synthetic-scene/frames", method="POST", body=payload, headers=headers)
        assert first_status == 201 and second_status == 200 and first["run_id"] == second["run_id"]
    finally:
        proc.terminate()
        proc.wait(timeout=5)
    proc = start()
    try:
        _, health = call("/api/v1/health")
        assert health["observation_count"] == 6 and health["database_schema"] >= 1
        print(json.dumps({"result": "PASS", "synthetic_capture_http": 201, "unauthenticated_http": 401,
                          "duplicate_ingestion_http": 200, "persisted_after_process_restart": 6,
                          "bind": "127.0.0.1", "live_cameras": "not_connected", "model_weights": "not_loaded"}))
    finally:
        proc.terminate()
        proc.wait(timeout=5)
