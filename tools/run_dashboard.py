"""Convenience local launcher. Generates a session key unless one is already set."""
import os
from pathlib import Path
import secrets
import sys
import argparse
import socket
from threading import Timer
import webbrowser
import http.client
import json
import time
import psutil

import uvicorn

from vop.config import load_config
from vop.service import create_app


def remembered_key(vault, candidate):
    from vop.contracts import ProviderError
    try:
        return vault.get("dashboard-access-key")
    except ProviderError:
        if (vault.root / "dashboard-access-key.dpapi").exists():
            raise  # A decryption failure must not silently rotate the existing key.
        vault.set("dashboard-access-key", candidate)
        return candidate


def trusted_listener(port):
    try:
        account = psutil.Process().username()
        for entry in psutil.net_connections(kind='tcp'):
            if entry.status != psutil.CONN_LISTEN or entry.laddr.ip != '127.0.0.1' or entry.laddr.port != port or not entry.pid:
                continue
            process = psutil.Process(entry.pid)
            if process.username() != account:
                return False
            for argument in process.cmdline():
                if argument.endswith('run_dashboard.py'):
                    path = Path(argument)
                    if not path.is_absolute(): path = Path(process.cwd()) / path
                    return path.resolve() == Path(__file__).resolve()
        return False
    except (psutil.Error, OSError):
        return False


def open_workspace(port, token):
    if not trusted_listener(port):
        raise OSError('Waiting for the owned VOP listener')
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.request('POST', '/api/v1/browser-ticket', headers={'Authorization': 'Bearer ' + token})
        response = connection.getresponse()
        body = response.read(4096)
        if response.status != 200:
            raise RuntimeError('The running app could not authenticate this launcher. Close VOP and open Start VOP again; do not change any keys.')
        path = json.loads(body)['url']
        if not path.startswith('/launch/') or '/' in path[len('/launch/'):]:
            raise RuntimeError('Unexpected launcher response')
        webbrowser.open(f'http://127.0.0.1:{port}' + path)
    finally:
        connection.close()


def open_when_ready(port, token):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            open_workspace(port, token)
            return
        except OSError:
            time.sleep(.5)
        except (RuntimeError, ValueError, KeyError):
            print('VOP could not open a signed-in workspace. Close VOP and reopen Start VOP. Your saved settings are retained.', flush=True)
            return
    print('VOP is taking longer to start. Open Start VOP again in a moment.', flush=True)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Start the local VOP browser dashboard")
    parser.add_argument("config", nargs="?", type=Path, default=root / "sample-config" / "phase1.json")
    parser.add_argument("--allow-live-sources", action="store_true")
    parser.add_argument("--allow-remote-inference", action="store_true", help="Compatibility flag; the dashboard already uses its explicitly selected worker")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--remember-access-key", action="store_true", help="Reuse a Windows DPAPI-protected operator key")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument('--show-access-key', action='store_true', help='Advanced: display the API/operator key for manual clients')
    parser.add_argument('--manual-worker', action='store_true', help='Disable automatic on-demand Antec recovery')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1–65535")
    path = args.config.resolve()
    token = os.environ.get("VOP_API_TOKEN") or secrets.token_urlsafe(32)
    if (args.remember_access_key or args.open_browser and os.name == 'nt') and not os.environ.get("VOP_API_TOKEN"):
        if os.name != "nt":
            parser.error("Remembered launcher access keys currently require Windows DPAPI")
        from vop.secrets import SecretStore
        try:
            token = remembered_key(SecretStore(), token)
        except Exception:
            parser.exit(1, 'VOP could not unlock its saved Windows settings. Close VOP, sign in with the same Windows account and try Start VOP again. No keys were replaced.\n')
    if args.open_browser:
        try:
            with socket.create_connection(('127.0.0.1', args.port), timeout=.5):
                pass
        except OSError:
            pass
        else:
            try:
                open_workspace(args.port, token)
            except (OSError, RuntimeError, ValueError, KeyError):
                parser.exit(1, 'VOP is already running but could not open your workspace. Close VOP and reopen Start VOP. No key entry is needed.\n')
            return
    print(f"VOP dashboard: http://127.0.0.1:{args.port}")
    if args.show_access_key:
        print('Advanced operator/API key:')
        print(token, flush=True)
    print('Open Start VOP for automatic sign-in. Saved setup is reused; Antec connects when needed. Press Ctrl+C to stop.', flush=True)
    app = create_app(load_config(path), token=token, allow_live_sources=args.allow_live_sources, allow_remote_inference=True, auto_recover=not args.manual_worker)
    if args.open_browser:
        opener = Timer(1, open_when_ready, args=(args.port, token))
        opener.daemon = True
        opener.start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
