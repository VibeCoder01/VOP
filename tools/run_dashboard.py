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
    args = parser.parse_args()
    path = args.config.resolve()
    token = os.environ.get("VOP_API_TOKEN") or secrets.token_urlsafe(32)
    print("VOP dashboard: http://127.0.0.1:8765")
    print("Local operator access key (shown intentionally for browser sign-in):")
    print(token, flush=True)
    print("Mock inference by default. Saved sampling resumes; live sources require the opt-in flag. Press Ctrl+C to stop.", flush=True)
    app = create_app(load_config(path), token=token, allow_live_sources=args.allow_live_sources)
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
