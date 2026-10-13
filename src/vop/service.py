"""Authenticated local FastHTML service; all source destinations are operator configured."""
import hmac
import json
import os
import sqlite3
from dataclasses import replace
from uuid import uuid4
from threading import Lock

from fasthtml.core import FastHTML
from fasthtml.components import H1, Main, P
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from vop.config import Settings, identifier
from vop.contracts import InferenceEngine, ProviderError
from vop.inference.mock import MockInferenceEngine
from vop.inputs.file_image import FileImageAdapter
from vop.inputs.sources import MAX_IMAGE_BYTES, SourceAdapters
from vop.pipeline import Pipeline
from vop.storage import Store


class OperatorAuth:
    def __init__(self, app, *, token: str, store: Store, pipeline: Pipeline):
        self.app, self.token, self.store = app, token.encode("ascii"), store
        self.pipeline = pipeline
        self.admission = Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        supplied = headers.get(b"authorization", b"")
        valid = supplied.startswith(b"Bearer ") and hmac.compare_digest(supplied[7:], self.token)
        if not valid:
            try:
                await run_in_threadpool(self.store.audit, "authentication", "denied")
            except sqlite3.Error:
                pass  # Auth stays fail-closed even when audit storage is unavailable.
            return await JSONResponse({"error": "authentication_required"}, status_code=401,
                                      headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"})(scope, receive, send)
        # No cookies, URL tokens or permissive CORS. Reject browser-originated cross-site calls.
        if b"origin" in headers:
            try:
                await run_in_threadpool(self.store.audit, "browser_origin", "denied")
            except sqlite3.Error:
                pass
            return await JSONResponse({"error": "browser_origin_denied"}, status_code=403)(scope, receive, send)
        async def secured_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"cache-control", b"no-store"),
                                      (b"x-content-type-options", b"nosniff"),
                                      (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")]
            await send(message)
        admitted = scope["method"] == "POST"
        if admitted and not self.admission.acquire(blocking=False):
            self.pipeline.skipped += 1
            await run_in_threadpool(self.store.audit, "capture_skipped", "overload")
            return await JSONResponse({"error": "overloaded"}, status_code=429)(scope, receive, secured_send)
        try:
            await self.app(scope, receive, secured_send)
        finally:
            if admitted:
                self.admission.release()


def create_app(settings: Settings, *, token: str | None = None,
               engine: InferenceEngine | None = None, capture=None, allow_live_sources: bool = False):
    token = token if token is not None else os.environ.get("VOP_API_TOKEN", "")
    if not isinstance(token, str) or len(token) < 32 or len(token) > 256 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Set VOP_API_TOKEN to a 32–256 character ASCII secret without whitespace")
    store = Store(settings.database)
    store.configure(settings)
    engine = engine or MockInferenceEngine(settings.mock_answers, settings.engine_id)
    capture = capture or SourceAdapters(allow_live_sources=allow_live_sources, timeout_seconds=settings.capture_timeout_seconds)
    pipeline = Pipeline(settings, engine, store, capture)

    async def provider_error(req, exc):
        code = {"source_not_found": 404, "source_disabled": 409, "overloaded": 429, "frame_conflict": 409}.get(exc.code, 422)
        return JSONResponse({"error": exc.code}, status_code=code)

    async def bad_request(req, exc):
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    async def database_error(req, exc):
        return JSONResponse({"error": "storage_unavailable"}, status_code=503)

    app = FastHTML(default_hdrs=False, sess_cls=None, secret_key=token,
                   middleware=[Middleware(OperatorAuth, token=token, store=store, pipeline=pipeline)],
                   exception_handlers={ProviderError: provider_error, ValueError: bad_request, sqlite3.Error: database_error})
    app.state.pipeline, app.state.store = pipeline, store

    @app.route("/", methods=["GET"])
    def index():
        return Main(H1("VOP Phase 1 service"), P("Authenticated foundation API. No dashboard or continuous capture."))

    @app.route("/api/v1/health", methods=["GET"])
    def health():
        return JSONResponse({"status": "ready", **store.health(), "in_flight": pipeline.busy.locked(),
                             "queue_depth": 0, "skipped_requests": pipeline.skipped,
                             "engine": {"id": engine.engine_id, "version": engine.engine_version,
                                        "synthetic": engine.synthetic, "capabilities": list(engine.capabilities())}})

    @app.route("/api/v1/sources", methods=["GET"])
    def sources():
        return JSONResponse({"sources": store.sources(tuple(pipeline.sources))})

    @app.route("/api/v1/sources/{source_id}/capture", methods=["POST"])
    async def capture_once(source_id: str):
        result = await run_in_threadpool(pipeline.run, source_id)
        return JSONResponse(result, status_code=201)

    @app.route("/api/v1/sources/{source_id}/frames", methods=["POST"])
    async def ingest(source_id: str, request: Request):
        pipeline.source(source_id)
        if request.headers.get("content-type", "").split(";")[0].strip().lower() not in ("image/jpeg", "image/png"):
            return JSONResponse({"error": "unsupported_media_type"}, status_code=415)
        frame_id = identifier(request.headers.get("x-frame-id", str(uuid4())))
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_IMAGE_BYTES:
                return JSONResponse({"error": "image_too_large"}, status_code=413)
            payload.extend(chunk)
        try:
            frame = await run_in_threadpool(FileImageAdapter().from_bytes, bytes(payload), source_id)
        except ProviderError as exc:
            # Persist failed ingestion without pretending a frame was successfully acquired.
            source = pipeline.source(source_id)
            result = await run_in_threadpool(pipeline.save_capture_error, source, exc)
            return JSONResponse(result, status_code=422)
        frame = replace(frame, frame_id=frame_id)
        result = await run_in_threadpool(pipeline.run, source_id, frame)
        return JSONResponse(result, status_code=200 if result["duplicate"] else 201)

    @app.route("/api/v1/observations", methods=["GET"])
    def observations(request: Request):
        source_id = request.query_params.get("source_id")
        if source_id and source_id not in pipeline.sources:
            raise ProviderError("source_not_found", "Source does not exist")
        after = int(request.query_params.get("after", "0"))
        limit = int(request.query_params.get("limit", "20"))
        if after < 0 or not 1 <= limit <= 100:
            raise ValueError("Invalid pagination")
        rows = store.observations(source_id, after=after, limit=limit)
        return JSONResponse({"observations": rows, "next_after": rows[-1]["sequence"] if rows else after})

    return app
