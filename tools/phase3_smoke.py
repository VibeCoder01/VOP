"""Actual subprocess HTTP/browser/alert/export/backup/restore smoke; synthetic only."""
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from process_cleanup import stop_process
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="vop-phase3-smoke-") as folder:
        folder = Path(folder)
        body = json.loads((root / "sample-config/phase1.json").read_text(encoding="utf-8"))
        body["database"] = "data/vop.sqlite3"
        config = folder / "config.json"
        config.write_text(json.dumps(body), encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        token, viewer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        env = {**os.environ, "VOP_API_TOKEN": token, "VOP_VIEWER_TOKEN": viewer}
        def api(route, credential=token):
            with urlopen(Request(base + route, headers={"Authorization": "Bearer " + credential}), timeout=10) as response:
                return json.load(response)
        def start(path):
            proc = subprocess.Popen([sys.executable, "-m", "vop", "serve", "--config", str(path), "--port", str(port)], cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for attempt in range(100):
                try:
                    api("/api/v1/health")
                    return proc
                except (URLError, OSError):
                    if proc.poll() is not None:
                        raise RuntimeError("Service startup failed")
                    time.sleep(0.05)
            stop_process(proc)
            raise RuntimeError("Service startup timed out")
        proc = start(config)
        browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def html(route):
            with browser.open(base + route, timeout=10) as response:
                return response.read().decode()
        def csrf(route="/release"):
            return re.search(r'name="csrf"[^>]*value="([^"]+)"', html(route))[1]
        def form(route, data):
            with browser.open(Request(base + route, data=urlencode(data).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=10) as response:
                return response.read().decode()
        try:
            form("/login", {"csrf": csrf("/login"), "access_key": token})
            form("/release/rules", {"csrf": csrf(), "id": "smoke-count", "source_id": "synthetic-scene", "question_id": "red_square", "kind": "count", "severity": "warning", "threshold": "0", "window_seconds": "3600", "enabled": "on"})
            form("/ui/sources/synthetic-scene/demo", {"csrf": csrf()})
            for _ in range(80):
                alerts = api("/api/v1/alerts")["alerts"]
                if alerts:
                    break
                time.sleep(0.1)
            assert len(alerts) == 1 and alerts[0]["payload"]["synthetic"]
            aid = alerts[0]["id"]
            form("/release/alerts/" + aid, {"csrf": csrf(), "action": "acknowledged", "note": "Smoke review"})
            assert api("/api/v1/alerts")["alerts"][0]["status"] == "acknowledged"
            exports = json.loads(html("/release/export?kind=events&format=json"))
            assert len(exports["rows"]) == 1 and exports["rows"][0]["provenance"]["synthetic"]
            csv = html("/release/export?kind=alerts&format=csv")
            assert "timezone" in csv and "smoke-count" in csv
            preview = form("/release/retention/preview", {"csrf": csrf(), "evidence": "30", "raw": "30", "audit": "365"})
            assert "Apply policy" in preview
            try:
                api("/release/config", viewer)
                raise AssertionError("Viewer received operator configuration")
            except HTTPError as exc:
                assert exc.code == 403
            count = api("/api/v1/health")["observation_count"]
        finally:
            stop_process(proc)
        subprocess.run([sys.executable, str(root / "tools/release.py"), "backup", "--config", str(config), "--output", str(folder / "backup")], cwd=root, check=True, stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, str(root / "tools/release.py"), "restore", "--input", str(folder / "backup"), "--output", str(folder / "restored")], cwd=root, check=True, stdout=subprocess.DEVNULL)
        proc = start(folder / "restored" / "config.json")
        try:
            assert api("/api/v1/health")["observation_count"] == count
            restored = api("/api/v1/alerts")["alerts"]
            assert len(restored) == 1 and restored[0]["id"] == aid and restored[0]["status"] == "acknowledged"
            print(json.dumps({"result": "PASS", "input": "synthetic", "model": "explicit mock", "alert_idempotency_restart": "passed", "acknowledgement": "persisted", "exports": ["CSV", "JSON"], "viewer_config_denial": 403, "retention_preview": "passed", "backup_restore_observations": count, "outbound_delivery": "not_configured", "cameras": "not_connected"}))
        finally:
            stop_process(proc)


if __name__ == "__main__":
    main()
