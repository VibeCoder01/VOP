"""Actual local HTTP/browser-session/state/evidence/restart smoke. Synthetic input only."""
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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="vop-phase2-smoke-") as folder:
        path = Path(folder) / "config.json"
        body = json.loads((root / "sample-config" / "phase1.json").read_text(encoding="utf-8"))
        body["database"] = "observations.sqlite3"
        path.write_text(json.dumps(body), encoding="utf-8")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        token, viewer = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        env = {**os.environ, "VOP_API_TOKEN": token, "VOP_VIEWER_TOKEN": viewer}
        def api(route, method="GET", credential=token):
            req = Request(base + route, method=method, headers={"Authorization": "Bearer " + credential})
            with urlopen(req, timeout=10) as response:
                return json.load(response)
        def start():
            proc = subprocess.Popen([sys.executable, "-m", "vop", "serve", "--config", str(path), "--port", str(port)],
                                    cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for attempt in range(100):
                try:
                    api("/api/v1/health")
                    return proc
                except (URLError, OSError):
                    if proc.poll() is not None:
                        raise RuntimeError("Service startup failed")
                    time.sleep(0.05)
            proc.terminate()
            proc.wait(timeout=5)
            raise RuntimeError("Service startup timed out")
        proc = start()
        try:
            browser = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            def html(route):
                with browser.open(base + route, timeout=10) as response:
                    return response.read().decode("utf-8")
            def csrf(route="/"):
                match = re.search(r'name="csrf"[^>]*value="([^"]+)"', html(route))
                assert match
                return match[1]
            def form(route, values):
                req = Request(base + route, data=urlencode(values).encode(), headers={"Content-Type": "application/x-www-form-urlencoded"})
                with browser.open(req, timeout=10) as response:
                    return response.status, response.read().decode("utf-8")
            form("/login", {"csrf": csrf("/login"), "access_key": token})
            assert "Overview" in html("/")
            form("/ui/sources/synthetic-scene/demo", {"csrf": csrf()})
            events = api("/api/v1/events")["events"]
            assert len(events) == 1 and events[0]["status"] == "closed"
            api("/api/v1/replay", "POST")
            assert api("/api/v1/events")["events"] == events
            form("/ui/sources/synthetic-scene", {"csrf": csrf(), "enabled": "on", "retain_evidence": "on", "sample_interval_seconds": "0"})
            run = api("/api/v1/sources/synthetic-scene/capture", "POST")["result"]
            evidence_url = f"/ui/evidence/synthetic-scene/{run['frame_id']}"
            with browser.open(base + evidence_url, timeout=10) as response:
                assert response.headers.get_content_type() == "image/png"
            try:
                api(evidence_url, credential=viewer)
                raise AssertionError("Viewer received restricted image evidence")
            except HTTPError as exc:
                assert exc.code == 403
            form(evidence_url + "/delete", {"csrf": csrf()})
            try:
                browser.open(base + evidence_url, timeout=10)
                raise AssertionError("Deleted evidence remains reachable")
            except HTTPError as exc:
                assert exc.code == 404
            for view in ("sources", "questions", "events", "metrics", "settings"):
                assert "VOP" in html("/?view=" + view)
            before = api("/api/v1/health")["observation_count"]
        finally:
            proc.terminate()
            proc.wait(timeout=5)
        proc = start()
        try:
            assert api("/api/v1/health")["observation_count"] == before
            assert len(api("/api/v1/events")["events"]) >= 1
            print(json.dumps({"result": "PASS", "browser_session_login": "passed", "csrf_forms": "passed",
                              "confirmed_closed_episode": "passed", "deterministic_replay": "passed",
                              "viewer_evidence_denial": 403, "deleted_evidence_http": 404,
                              "persisted_observations_after_restart": before, "views": 6,
                              "input": "synthetic", "model": "explicit mock", "live_cameras": "not_connected"}))
        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
