"""Loopback inference worker with a supervised model child, one slot and no queue."""
from collections import OrderedDict, deque
from datetime import timedelta
import hmac
import asyncio
import json
import multiprocessing
import os
from threading import Lock
from time import monotonic

from fasthtml.core import FastHTML
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from vop.contracts import AnswerKind, ProviderError, Status, failed, infer, utcnow
from vop.inference.liquid_d1 import CHECKPOINT_REVISION
from vop.worker_protocol import MAX_BODY, MAX_RESPONSE, decode_request, encode


def model_child(connection, config):
    # Third-party diagnostics may contain paths/data; only sanitized status crosses the boundary.
    with open(os.devnull, "w") as quiet:
        os.dup2(quiet.fileno(), 1)
        os.dup2(quiet.fileno(), 2)
        try:
            if config["kind"] == "mock":
                from vop.inference.mock import MockInferenceEngine
                engine = MockInferenceEngine(config.get("answers", {}), config["engine_id"])
                runtime = {"device": "mock", "precision": None}
            else:
                from vop.inference.liquid_d1 import LiquidD1InferenceAdapter
                import psutil
                minimum = 24 if config["device"] == "cpu" else 8
                if psutil.virtual_memory().available < minimum * 1024**3:
                    connection.send({"error": "host_capacity"})
                    return
                if config["device"] == "cuda:0":
                    import torch
                    minimum_vram = 14 if config["precision"] == "float32" else 8
                    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < minimum_vram * 1024**3:
                        connection.send({"error": "gpu_capacity"})
                        return
                engine = LiquidD1InferenceAdapter(device=config["device"], precision=config["precision"])
                engine.load(allow_model_download=True, accept_model_risk=True, cache_dir=config["cache_dir"])
                runtime = {"device": str(next(engine.model.parameters()).device), "precision": str(next(engine.model.parameters()).dtype)}
                if config["device"] == "cuda:0":
                    import torch
                    runtime["gpu_name"] = torch.cuda.get_device_name(0)
            connection.send({"ready": runtime})
            while True:
                request = connection.recv()
                if request is None:
                    break
                if config["kind"] == "mock" and config.get("mock_delay_seconds"):
                    from time import sleep
                    sleep(config["mock_delay_seconds"])
                outcome = infer(engine, request)
                connection.send(outcome)
                if outcome.error and outcome.error.code == "inference_oom":
                    break
        except Exception:
            try:
                connection.send({"error": "model_worker_failed"})
            except (OSError, EOFError):
                pass
        finally:
            connection.close()


class SupervisedEngine:
    def __init__(self, config, *, timeout_seconds=30, load_timeout=180):
        if config.get("kind") not in ("mock", "liquid-d1-3b") or not 0 < timeout_seconds <= 300 or not 0 < load_timeout <= 600:
            raise ValueError("Invalid worker backend or time limit")
        self.config, self.timeout_seconds, self.load_timeout = dict(config), timeout_seconds, load_timeout
        self.engine_id = config.get("engine_id", "liquid-d1-3b")
        self.synthetic = config["kind"] == "mock"
        self.engine_version = "deterministic-mock-v1" if self.synthetic else CHECKPOINT_REVISION
        self.process = self.connection = None
        self.lock = Lock()
        self.starts = deque(maxlen=3)
        self.runtime = None
        self.last_error = None
        self.skipped = 0

    def capabilities(self):
        return tuple(AnswerKind)

    def close(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2)
            self.process.close()
        if self.connection:
            self.connection.close()
        self.process = self.connection = None
        self.runtime = None

    def prepare(self, timeout=None):
        if self.process and self.process.is_alive() and self.runtime:
            return
        self.close()
        now = monotonic()
        if len(self.starts) == 3 and now - self.starts[0] < 60:
            raise ProviderError("worker_cooldown", "Repeated worker failures; wait for recovery cooldown")
        self.starts.append(now)
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        self.connection = parent
        self.process = ctx.Process(target=model_child, args=(child, self.config), daemon=True)
        self.process.start()
        child.close()
        try:
            if not parent.poll(min(timeout or self.load_timeout, self.load_timeout)):
                raise ProviderError("model_load_timeout", "Model load exceeded its hard deadline", Status.TIMEOUT)
            message = parent.recv()
            if not isinstance(message, dict) or "ready" not in message:
                code = message["error"] if isinstance(message, dict) and message.get("error") in ("gpu_capacity", "host_capacity") else "model_load_failed"
                raise ProviderError(code, "Model could not be loaded on requested device")
            self.runtime = message["ready"]
            if not self.synthetic and self.runtime["device"] != self.config["device"]:
                raise ProviderError("device_mismatch", "Model did not load on the requested device")
            self.last_error = None
        except (EOFError, OSError):
            self.close()
            raise ProviderError("model_load_failed", "Model worker terminated during load") from None
        except ProviderError as exc:
            self.last_error = exc.code
            self.close()
            raise

    def infer(self, request):
        if not self.lock.acquire(False):
            self.skipped += 1
            return failed(request, self, ProviderError("overloaded", "Worker slot is busy"))
        try:
            budget = min(self.timeout_seconds, (request.deadline_utc - utcnow()).total_seconds() if request.deadline_utc else self.timeout_seconds)
            if budget <= 0:
                raise ProviderError("deadline", "Request expired", Status.TIMEOUT)
            started = monotonic()
            self.prepare(budget)
            budget -= monotonic() - started
            if budget <= 0:
                raise ProviderError("deadline", "Request expired during model load", Status.TIMEOUT)
            self.connection.send(request)
            if not self.connection.poll(budget):
                self.close()
                raise ProviderError("worker_timeout", "Model child was terminated at its hard deadline", Status.TIMEOUT)
            outcome = self.connection.recv()
            from vop.contracts import InferenceResult
            if not isinstance(outcome, InferenceResult):
                self.close()
                raise ProviderError("worker_crashed", "Model child failed")
            self.last_error = None if outcome.status == Status.SUCCESS else "inference_failed"
            if outcome.error and outcome.error.code in ("inference_oom", "inference_exception"):
                self.close()
            return outcome
        except (OSError, EOFError):
            self.close()
            self.last_error = "worker_crashed"
            return failed(request, self, ProviderError("worker_crashed", "Model child terminated"))
        except ProviderError as exc:
            self.last_error = exc.code
            return failed(request, self, exc)
        finally:
            self.lock.release()


def create_worker_app(engine, *, worker_id, token):
    from vop.config import identifier
    identifier(worker_id)
    if len(token) < 32 or len(token) > 256 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Worker token must be 32–256 ASCII characters without whitespace")
    cache = OrderedDict()
    admission = Lock()
    async def lifespan(app):
        try:
            await run_in_threadpool(engine.prepare)
        except ProviderError:
            pass  # Health truthfully reports unavailable; an explicit request can retry after cooldown.
        try:
            yield
        finally:
            engine.close()
    app = FastHTML(default_hdrs=False, sess_cls=None, lifespan=lifespan)
    app.state.engine = engine

    def allowed(request):
        headers = request.headers
        return (headers.get("host", "").split(":")[0] in ("127.0.0.1", "testserver") and not headers.get("origin")
                and hmac.compare_digest(headers.get("authorization", "").encode(), ("Bearer " + token).encode()))

    @app.route("/health", methods=["GET"])
    def health(request):
        if not allowed(request):
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        return JSONResponse({"protocol": 1, "worker_id": worker_id, "engine_id": engine.engine_id, "engine_version": engine.engine_version,
                             "synthetic": engine.synthetic, "capabilities": list(engine.capabilities()), "ready": engine.runtime is not None and engine.process is not None and engine.process.is_alive(),
                             "runtime": engine.runtime, "busy": engine.lock.locked(), "queue_depth": 0, "skipped": engine.skipped,
                             "error": engine.last_error, "utc": utcnow().isoformat()})

    @app.route("/infer", methods=["POST"])
    async def inference(request):
        if not allowed(request):
            return JSONResponse({"error": "authentication_required"}, status_code=401)
        if request.headers.get("content-type") != "application/json":
            return JSONResponse({"error": "json_required"}, status_code=415)
        if not admission.acquire(False):
            engine.skipped += 1
            return JSONResponse({"error": "overloaded"}, status_code=429)
        try:
            raw = bytearray()
            async def read_body():
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > MAX_BODY:
                        raise ValueError("body_limit")
                    raw.extend(chunk)
            try:
                await asyncio.wait_for(read_body(), timeout=10)
            except ValueError:
                return JSONResponse({"error": "request_too_large"}, status_code=413)
            except (TimeoutError, asyncio.TimeoutError):
                return JSONResponse({"error": "body_timeout"}, status_code=408)
            try:
                body = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                value = await run_in_threadpool(decode_request, body, worker_id)
            except Exception:
                return JSONResponse({"error": "invalid_request"}, status_code=400)
            raw.clear()
            now = monotonic()
            for key in list(cache):
                if cache[key][0] < now:
                    cache.pop(key)
            rid = body["request_id"]
            if rid in cache:
                return Response(cache[rid][1], media_type="application/json")
            result = await run_in_threadpool(engine.infer, value)
            from dataclasses import replace
            def sanitized(error):
                return replace(error, message="Model worker reported a processing failure") if error else None
            result = replace(result, error=sanitized(result.error), answers=tuple(replace(a, error=sanitized(a.error)) for a in result.answers))
            encoded = encode({"protocol": 1, "worker_id": worker_id, "request_id": rid, "result": result})
            if len(encoded) > MAX_RESPONSE:
                return JSONResponse({"error": "response_too_large"}, status_code=502)
            # ponytail: at most 32 MiB of result cache; persistent distributed replay ledger if ever required.
            cache[rid] = (now + 30, encoded)
            while len(cache) > 16:
                cache.popitem(last=False)
            return Response(encoded, media_type="application/json")
        finally:
            admission.release()
    return app
