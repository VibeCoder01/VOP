import argparse
import json
import sys

from vop.contracts import InferenceRequest, ProviderError, Status, infer, json_default
from vop.environment import inventory
from vop.examples import MOCK_ANSWERS, questions
from vop.inference.mock import MockInferenceEngine
from vop.inputs.file_image import FileImageAdapter


def positive(value: str) -> float:
    number = float(value)
    if not 0 < number < float("inf"):
        raise argparse.ArgumentTypeError("Must be finite and greater than zero")
    return number


def repeats(value: str) -> int:
    number = int(value)
    if number < 3:
        raise argparse.ArgumentTypeError("At least three warm repeats are required")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VOP Phase 0: offline still-image contracts and opt-in feasibility")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Synthetic mock only; never downloads weights")
    demo.add_argument("--image", required=True)
    demo.add_argument("--engine", choices=["mock"], default="mock")
    check = sub.add_parser("check-env", help="Read machine/memory inventory without model imports")
    check.add_argument("--disk-path", default=".")
    bench = sub.add_parser("benchmark", help="Explicit model-code/download/RAM consent required")
    bench.add_argument("--image", required=True)
    bench.add_argument("--engine", choices=["liquid-d1-3b"], default="liquid-d1-3b")
    bench.add_argument("--allow-model-download", action="store_true")
    bench.add_argument("--accept-model-risk", action="store_true", help="Consent to checkpoint Python execution and RAM risk")
    bench.add_argument("--override-preflight", action="store_true", help="Override conservative preflight only, not runtime RAM watchdog")
    bench.add_argument("--reference-dell", action="store_true", help="Require Windows/Dell/i5-10310U/16 GiB target identity")
    bench.add_argument("--cache-dir", default=".cache/huggingface")
    bench.add_argument("--output-dir", default="reports/local")
    bench.add_argument("--timeout-seconds", type=positive, default=900)
    bench.add_argument("--repeats", type=repeats, default=3)
    args = parser.parse_args(argv)
    try:
        if args.command == "check-env":
            output = inventory(args.disk_path)
            code = 0
        elif args.command == "demo":
            frame = FileImageAdapter().read(args.image)
            output = infer(MockInferenceEngine(MOCK_ANSWERS), InferenceRequest(frame, questions()[:3]))
            code = 0 if output.status == Status.SUCCESS else 1
        else:
            from vop.benchmark import WARNING, run_benchmark
            print(WARNING, file=sys.stderr)
            output = run_benchmark(args)
            code = 0 if output["outcome"] == "passed" else 2
        print(json.dumps(output, indent=2, default=json_default, allow_nan=False))
        return code
    except (ProviderError, OSError, ValueError) as exc:
        error = exc if isinstance(exc, ProviderError) else ProviderError("cli_failure", str(exc))
        print(json.dumps({"status": error.status, "error": error}, default=json_default), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
