"""Explicit foreground loopback worker; real model execution requires both consent flags."""
import argparse
import json
import os
from pathlib import Path

from vop.worker import SupervisedEngine, create_worker_app


def main():
    parser = argparse.ArgumentParser(description="VOP supervised worker (foreground, loopback only)")
    parser.add_argument("--worker-id", required=True)
    parser.add_argument("--port", type=int, default=8878)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--backend", choices=("liquid-d1-3b", "mock"), default="liquid-d1-3b")
    parser.add_argument("--device", choices=("cpu", "cuda:0"), default="cpu")
    parser.add_argument("--precision", choices=("float32", "bfloat16", "float16"), default="float32")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--accept-model-risk", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--mock-delay-seconds", type=float, default=0, help="Synthetic overload-test delay only")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Invalid port")
    if not 0 <= args.mock_delay_seconds <= 1 or args.backend != "mock" and args.mock_delay_seconds:
        parser.error("Mock delay is only supported for synthetic test workers (0–1 seconds)")
    if os.name != "nt" and args.token_file.stat().st_mode & 0o077:
        parser.error("Worker token file must be accessible only to its owner (chmod 600)")
    if args.backend != "mock" and (not args.allow_model_download or not args.accept_model_risk or not args.cache_dir):
        parser.error("Real model requires --cache-dir, --allow-model-download and --accept-model-risk")
    if args.backend != "mock" and args.device == "cpu" and args.precision != "float32":
        parser.error("Local CPU worker requires float32 precision")
    config = {"kind": args.backend, "device": args.device, "precision": args.precision, "cache_dir": str(args.cache_dir),
              "mock_delay_seconds": args.mock_delay_seconds, "engine_id": "mock-worker" if args.backend == "mock" else "liquid-d1-3b", "answers": {"human_present": False, "red_square": True, "background": "white", "brightness": 2.0}}
    engine = SupervisedEngine(config, timeout_seconds=args.timeout_seconds)
    import uvicorn
    app = create_worker_app(engine, worker_id=args.worker_id, token=args.token_file.read_text(encoding="utf-8").strip())
    print(json.dumps({"worker_id": args.worker_id, "bind": "127.0.0.1", "port": args.port, "backend": args.backend, "device_requested": args.device}), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
