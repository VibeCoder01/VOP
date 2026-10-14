"""Authenticated local FastHTML service; all source destinations are operator configured."""
import json
import os
import sqlite3
from dataclasses import replace
from uuid import uuid4

from fasthtml.core import FastHTML
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from vop.config import Settings, identifier
from vop.contracts import InferenceEngine, ProviderError, utcnow
from vop.inference.mock import MockInferenceEngine
from vop.inputs.file_image import FileImageAdapter
from vop.inputs.sources import MAX_IMAGE_BYTES, SourceAdapters
from vop.pipeline import Pipeline
from vop.storage import Store
from vop.browser_auth import BrowserAuth
from vop.dashboard import install_dashboard
from vop.sampling import Sampler
from vop.reliable import Reliable


def create_app(settings: Settings, *, token: str | None = None,
               engine: InferenceEngine | None = None, capture=None, allow_live_sources: bool = False,
               viewer_token: str | None = None, allow_remote_inference: bool = False):
    token = token if token is not None else os.environ.get("VOP_API_TOKEN", "")
    if not isinstance(token, str) or len(token) < 32 or len(token) > 256 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Set VOP_API_TOKEN to a 32–256 character ASCII secret without whitespace")
    viewer_token = viewer_token if viewer_token is not None else os.environ.get("VOP_VIEWER_TOKEN")
    if viewer_token and (len(viewer_token) < 32 or len(viewer_token) > 256 or not viewer_token.isascii() or any(c.isspace() for c in viewer_token) or viewer_token == token):
        raise ValueError("Viewer key must be a distinct 32–256 character ASCII secret")
    store = Store(settings.database)
    store.configure(settings)
    saved_profile = None
    with store.connection() as db:
        row = db.execute("SELECT value_json FROM release_settings WHERE id='engine_profile'").fetchone()
        saved_profile = json.loads(row[0]) if row else None
    active_profile = saved_profile or settings.engine or {"kind": "mock", "id": settings.engine_id, "answers": settings.mock_answers}
    if engine is None:
        if active_profile["kind"] == "worker":
            from vop.inference.remote import RemoteInferenceEngine
            engine = RemoteInferenceEngine(active_profile, allow_remote=allow_remote_inference)
        else:
            engine = MockInferenceEngine(active_profile["answers"], active_profile["id"])
    if isinstance(engine, MockInferenceEngine):
        for source_id, qid, version, value in store.mock_values():
            engine.configure_source_answer(source_id, qid, version, value)
    capture = capture or SourceAdapters(allow_live_sources=allow_live_sources, timeout_seconds=settings.capture_timeout_seconds)
    pipeline = Pipeline(settings, engine, store, capture)
    pipeline.engine_profile = active_profile
    from vop.integration_ui import restore_cameras
    restore_cameras(store, settings, pipeline)
    store.replay_all()
    sampler = Sampler(pipeline)
    reliable = Reliable(store, settings, pipeline)
    async def lifespan(app):
        sampler.start()
        reliable.start()
        try:
            yield
        finally:
            sampler.stop()
            reliable.stop()

    async def provider_error(req, exc):
        code = {"source_not_found": 404, "source_disabled": 409, "overloaded": 429, "frame_conflict": 409}.get(exc.code, 422)
        if "text/html" in req.headers.get("accept", "") and hasattr(app.state, "render_error"):
            from fasthtml.core import to_xml
            from starlette.responses import HTMLResponse
            message = "Another capture or inference is running. Wait for it to finish, then return to setup and retry." if exc.code == "overloaded" else exc.message
            return HTMLResponse(to_xml(app.state.render_error(req, message)), status_code=code)
        return JSONResponse({"error": exc.code}, status_code=code)

    async def bad_request(req, exc):
        if "text/html" in req.headers.get("accept", "") and hasattr(app.state, "render_error"):
            from fasthtml.core import to_xml
            from starlette.responses import HTMLResponse
            return HTMLResponse(to_xml(app.state.render_error(req, str(exc))), status_code=400)
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    async def database_error(req, exc):
        return JSONResponse({"error": "storage_unavailable"}, status_code=503)

    app = FastHTML(default_hdrs=False, sess_cls=None, secret_key=token,
                   middleware=[Middleware(SessionMiddleware, secret_key=token, session_cookie="vop_session", max_age=3600, same_site="strict"),
                               Middleware(BrowserAuth, token=token, viewer_token=viewer_token, store=store, pipeline=pipeline)],
                   lifespan=lifespan,
                   exception_handlers={ProviderError: provider_error, ValueError: bad_request, sqlite3.Error: database_error})
    app.state.pipeline, app.state.store = pipeline, store
    app.state.sampler = sampler
    app.state.reliable = reliable
    install_dashboard(app, settings, store, pipeline, engine, token, viewer_token)
    from vop.release_ui import install_release
    install_release(app, settings, store, pipeline, reliable)
    from vop.integration_ui import install_integration
    install_integration(app, settings, store, pipeline)

    @app.route("/api/v1/health", methods=["GET"])
    def health():
        return JSONResponse({"status": "ready", **store.health(), "in_flight": pipeline.busy.locked(),
                             "queue_depth": 0, "skipped_requests": pipeline.skipped,
                             "sampling_error": sampler.last_error,
                             "rules_error": reliable.last_error,
                             "engine": {"id": pipeline.engine.engine_id, "version": pipeline.engine.engine_version,
                                        "synthetic": pipeline.engine.synthetic, "capabilities": list(pipeline.engine.capabilities()),
                                        "worker_health": getattr(pipeline.engine, "last_health", None),
                                        "remote_consent": getattr(pipeline.engine, "allow_remote", False)}})

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

    @app.route("/api/v1/events", methods=["GET"])
    def events(request: Request):
        source_id = request.query_params.get("source_id")
        return JSONResponse({"events": store.events(source_id)})

    @app.route("/api/v1/metrics", methods=["GET"])
    def metrics(request: Request):
        source_id = request.query_params.get("source_id")
        values = []
        for sid in pipeline.sources:
            if source_id and source_id != sid:
                continue
            for record in store.questions(sid):
                q = record["spec"]
                values.append({"source_id": sid, "question_id": q.question_id, "question_version": q.version,
                               "summary": store.summary(sid, q.question_id, q.version, kind=q.kind, as_of=utcnow(),
                                                        timezone_name=settings.timezone_name)})
        return JSONResponse({"metrics": values})

    @app.route("/api/v1/replay", methods=["POST"])
    async def replay_history():
        if pipeline.busy.locked():
            raise ProviderError("overloaded", "Replay requires an idle inference slot")
        await run_in_threadpool(store.replay_all)
        return JSONResponse({"status": "replayed", "events": store.event_count()})

    return app
