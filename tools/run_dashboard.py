"""Convenience local launcher. Generates a session key unless one is already set."""
import os
from pathlib import Path
import secrets
import sys
import argparse

import uvicorn

from vop.config import load_config
from vop.service import create_app


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Start the local VOP browser dashboard")
    parser.add_argument("config", nargs="?", type=Path, default=root / "sample-config" / "phase1.json")
    parser.add_argument("--allow-live-sources", action="store_true")
    parser.add_argument("--allow-remote-inference", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1–65535")
    path = args.config.resolve()
    token = os.environ.get("VOP_API_TOKEN") or secrets.token_urlsafe(32)
    print(f"VOP dashboard: http://127.0.0.1:{args.port}")
    print("Local operator access key (shown intentionally for browser sign-in):")
    print(token, flush=True)
    print("Mock inference by default. Saved sampling resumes; live sources require the opt-in flag. Press Ctrl+C to stop.", flush=True)
    app = create_app(load_config(path), token=token, allow_live_sources=args.allow_live_sources, allow_remote_inference=args.allow_remote_inference)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
