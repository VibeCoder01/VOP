"""Convenience local launcher. Generates a session key unless one is already set."""
import os
from pathlib import Path
import secrets
import sys
import argparse
import socket
from threading import Timer
import webbrowser

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


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Start the local VOP browser dashboard")
    parser.add_argument("config", nargs="?", type=Path, default=root / "sample-config" / "phase1.json")
    parser.add_argument("--allow-live-sources", action="store_true")
    parser.add_argument("--allow-remote-inference", action="store_true", help="Compatibility flag; the dashboard already uses its explicitly selected worker")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--remember-access-key", action="store_true", help="Reuse a Windows DPAPI-protected operator key")
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1–65535")
    path = args.config.resolve()
    if args.open_browser:
        try:
            with socket.create_connection(("127.0.0.1", args.port), timeout=.5):
                print("A local app is already listening on this port. Opening its existing page.")
            webbrowser.open(f"http://127.0.0.1:{args.port}/")
            return
        except OSError:
            pass
    token = os.environ.get("VOP_API_TOKEN") or secrets.token_urlsafe(32)
    if args.remember_access_key and not os.environ.get("VOP_API_TOKEN"):
        if os.name != "nt":
            parser.error("Remembered launcher access keys currently require Windows DPAPI")
        from vop.secrets import SecretStore
        token = remembered_key(SecretStore(), token)
    print(f"VOP dashboard: http://127.0.0.1:{args.port}")
    print("Local operator access key (shown intentionally for browser sign-in):")
    print(token, flush=True)
    print("Mock inference by default. Saved sampling resumes; live sources require the opt-in flag. Press Ctrl+C to stop.", flush=True)
    app = create_app(load_config(path), token=token, allow_live_sources=args.allow_live_sources, allow_remote_inference=True)
    if args.open_browser:
        opener = Timer(1, webbrowser.open, args=(f"http://127.0.0.1:{args.port}/",))
        opener.daemon = True
        opener.start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
