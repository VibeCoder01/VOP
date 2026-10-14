"""Operator-owned engine profiles and protected camera setup. No credentials in SQLite."""
from dataclasses import replace
import ipaddress
import json
import secrets as random_secrets
from urllib.parse import urlsplit

from fasthtml.components import A, Button, Details, Form, H2, Input, Option, P, Pre, Section, Select, Summary
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse

from vop.config import SourceSpec, identifier
from vop.contracts import AnswerKind, ProviderError, QuestionSpec
from vop.dashboard import field, hidden, evidence_image
from vop.inference.liquid_d1 import CHECKPOINT_REVISION
from vop.inference.mock import MockInferenceEngine
from vop.inference.remote import RemoteInferenceEngine, profile
from vop.inputs.sources import SourceAdapters
from vop.preprocessing import preprocess
from vop.secrets import SecretStore, reference
from vop.storage import dumps


def worker_health_content(health):
    runtime = health.get("runtime") or {}
    if health.get("ready"):
        message = "Worker ready — " + ("synthetic mock" if health.get("synthetic") else str(runtime.get("gpu_name") or runtime.get("device") or "model loaded"))
    else:
        message = "Worker unavailable. Start an antec session below, or check your existing worker and tunnel."
    return [P(message, role="status"), P("Device: " + str(runtime.get("device", "not connected")) + " · Precision: " + str(runtime.get("precision") or "not reported")),
            P(("Processing another image" if health.get("busy") else "No image is currently being processed") if health.get("ready") else "Processing status is unavailable"),
            Details(Summary("Connection details"), Pre(dumps(health)))]


def camera_source(record):
    model = record["model"]
    if model not in ("C200", "C210", "C510W"):
        raise ValueError("Unsupported pilot camera model")
    sid = identifier(record["source_id"])
    options = {"endpoint_secret_ref": reference(record["endpoint_ref"]), "secret_ref": reference(record["credentials_ref"]), "allowed_hosts": record["allowed_hosts"]}
    if record.get("privacy_masks"):
        options["privacy_masks"] = record["privacy_masks"]
    return SourceSpec(sid, "Tapo " + model, "rtsp", options,
                      (QuestionSpec("human_present", "1", "Is there a human in the picture?", AnswerKind.BINARY),), enabled=False)


def restore_cameras(store, settings, pipeline):
    with store.connection() as db:
        rows = db.execute("SELECT value_json FROM release_settings WHERE id LIKE 'camera_profile:%'").fetchall()
    for row in rows:
        source = camera_source(json.loads(row[0]))
        store.configure(replace(settings, sources=(source,)))
        target = pipeline.removed_sources if store.is_removed(source.source_id) else pipeline.sources
        target[source.source_id] = source


def install_integration(app, settings, store, pipeline):
    secrets = SecretStore()
    app.state.secrets = secrets
    def operator(request):
        return request.scope.get("auth_role") == "operator"
    def busy():
        if not pipeline.busy.acquire(False):
            raise ProviderError("overloaded", "Stop or wait for the current capture/inference before changing profiles")

    @app.route("/integration", methods=["GET"])
    def integration(request):
        if not operator(request):
            return JSONResponse({"error": "operator_required"}, status_code=403)
        csrf = request.scope["session"].setdefault("csrf", random_secrets.token_urlsafe(24))
        current = pipeline.engine_profile
        worker = current if current["kind"] == "worker" else {}
        cams = [s for s in list(pipeline.sources.values()) if s.kind == "rtsp"]
        saved_cams = [s for s in cams if s.settings.get("endpoint_secret_ref")]
        selected_id = request.query_params.get("camera")
        selected = next((s for s in saved_cams if s.source_id == selected_id), None) if selected_id else (saved_cams[0] if saved_cams and "new_camera" not in request.query_params else None)
        if selected_id and selected is None:
            raise ValueError("Saved camera setup does not exist")
        endpoint, username, camera_notice = "", "", "Add a new camera."
        if selected:
            camera_notice = "Editing saved setup: " + selected.source_id
            try:
                endpoint = secrets.get(selected.settings["endpoint_secret_ref"])
                username = secrets.camera(selected.settings["secret_ref"])["username"]
            except ProviderError:
                camera_notice += ". Protected values are unavailable; re-enter them for this account."
        model = selected.name.removeprefix("Tapo ") if selected else "C200"
        session = app.state.worker_session.status()
        session_message = "No app-managed antec session is running."
        if session["active"]:
            from zoneinfo import ZoneInfo
            session_message = "Session requested until " + session["expires_at"].astimezone(ZoneInfo(settings.timezone_name)).strftime("%H:%M %Z") + ". Test worker health to confirm it is ready."
        content = [Section(H2("Selected inference backend"), P("Engine: " + pipeline.engine.engine_id), Details(Summary("Saved backend details"), Pre(dumps(current))),
                    P("Remote consent is active for this process." if getattr(pipeline.engine, "allow_remote", False) else "Remote image transmission is not enabled. Mock/local configuration is explicit."),
                    P("Worker profiles use a local loopback endpoint reached directly or through an SSH tunnel. Camera location and model location are independent.")),
                   Section(H2("Antec connection"), P(session_message, role="status"),
                    P("Start a timed GPU session and its SSH tunnel. The previous llama workload is restored at the end, on Stop, or when the connection closes. Camera capture and image transmission stay separate controls."),
                    Form(hidden(csrf), Select(*(Option(str(m) + " minutes", value=str(m)) for m in (15, 30, 60)), name="minutes", aria_label="Session duration"),
                         field("I authorise temporarily pausing antec's llama workload and restoring it when this session ends", "pause_consent", "on", type="checkbox"),
                         Button("Start antec session", disabled=session["active"]), method="post", action="/integration/session/start"),
                    Form(hidden(csrf), Button("Stop session and restore workload", disabled=not session["active"]), method="post", action="/integration/session/stop")),
                   Section(H2("Image transmission permission"),
                    P("Allowed for this app session" if getattr(pipeline.engine, "allow_remote", False) else "Off — camera images cannot reach the worker yet", role="status"),
                    Form(hidden(csrf), field("Allow preprocessed camera images to the currently selected worker", "allow", "on", type="checkbox", checked=getattr(pipeline.engine, "allow_remote", False)),
                         Button("Save image permission"), method="post", action="/integration/consent")),
                   Section(H2("Choose backend"), Form(hidden(csrf),
                    Select(Option("Local mock — no vision", value="mock", selected=current["kind"] == "mock"), Option("Authenticated worker", value="worker", selected=current["kind"] == "worker"), name="kind", aria_label="Backend"),
                    field("Engine ID", "engine_id", worker.get("id", "liquid-d1-3b"), required=True),
                    field("Model revision", "version", worker.get("version", CHECKPOINT_REVISION)),
                    field("Worker identity", "worker_id", worker.get("worker_id", "antec-d1")),
                    field("Worker loopback URL", "url", worker.get("url", "http://127.0.0.1:8878")),
                    Select(Option("SSH tunnel to another host", value="ssh", selected=worker.get("transport") != "local"), Option("Worker on this machine", value="local", selected=worker.get("transport") == "local"), name="transport", aria_label="Worker transport"),
                    field("Worker secret reference", "secret_ref", worker.get("secret_ref", "antec-worker")),
                    field("Worker access key (blank keeps saved key)", "worker_token", type="password", autocomplete="new-password"),
                    field("Worker is synthetic (only for mock-worker tests)", "synthetic", "on", type="checkbox", checked=worker.get("synthetic", False)),
                    field("I authorise sending preprocessed images to this selected worker for this process", "remote_consent", "on", type="checkbox"),
                    Button("Save and select backend"), method="post", action="/integration/engine")),
                   Form(hidden(csrf), Button("Test worker identity and health (no images)"), method="post", action="/integration/health"),
                   Section(H2("Protected Tapo setup"), P("Credentials are protected locally and never saved in the configuration or audit. Saving does not connect or start sampling. A blank password preserves the existing camera credentials. Retry setup and connection tests as needed."),
                    P("Use a different source ID for each camera, such as tapo-c200 and tapo-c210. Reusing an ID updates that camera's setup."),
                    P(camera_notice),
                    *(P(A("Edit " + s.source_id, href="/integration?camera=" + s.source_id)) for s in saved_cams),
                    P(A("Add another camera", href="/integration?new_camera=1")),
                    Form(hidden(csrf), field("Camera source ID", "source_id", selected.source_id if selected else "", placeholder="tapo-c200", required=True),
                         Select(*(Option(m, value=m, selected=m == model) for m in ("C200", "C210", "C510W")), name="model", aria_label="Camera model"),
                         field("Camera RTSP endpoint (LAN IP, no credentials)", "endpoint", endpoint, placeholder="rtsp://192.168.1.100:554/stream1", required=True),
                         field("Camera account username", "username", username, autocomplete="username"),
                         field("Camera account password (blank keeps saved credentials)", "password", type="password", autocomplete="new-password"),
                         Button("Save protected camera setup"), method="post", action="/integration/camera")),
                   Section(H2("Camera connection tests"),
                         *(Form(hidden(csrf), P(s.name + " · " + s.source_id),
                                field("I authorise one local camera capture; no image is sent to a model", "capture_consent", "on", type="checkbox", id="consent-" + s.source_id),
                                Button("Test camera connection"), method="post", action=f"/integration/cameras/{s.source_id}/test") for s in cams),
                         P("For normal inference, enable the source in Sources and explicitly allow live capture at startup. Remote inference additionally requires the separate consent above. Saved sampling does not bypass these checks."))]
        return app.state.page("Engine and camera setup", request, content, view="settings", notice=request.query_params.get("notice"))

    @app.route("/integration/session/start", methods=["POST"])
    async def session_start(request):
        form = await request.form()
        if "pause_consent" not in form:
            raise ValueError("Tick the pause-and-restore permission before starting a session")
        engine = pipeline.engine
        if not isinstance(engine, RemoteInferenceEngine) or engine.config["worker_id"] != "antec-d1" or engine.config["transport"] != "ssh" or engine.config["url"] != "http://127.0.0.1:8878" or engine.engine_id != "liquid-d1-3b" or engine.engine_version != CHECKPOINT_REVISION or engine.synthetic:
            raise ValueError("Select the real antec-d1 SSH backend at http://127.0.0.1:8878 before starting its session")
        await run_in_threadpool(app.state.worker_session.start, int(form.get("minutes", "15")))
        store.audit("worker_session", "start_requested")
        return RedirectResponse("/integration?notice=Antec+session+starting.+Test+worker+health+in+a+few+seconds.", status_code=303)

    @app.route("/integration/session/stop", methods=["POST"])
    async def session_stop(request):
        await run_in_threadpool(app.state.worker_session.stop)
        store.audit("worker_session", "stop_requested")
        return RedirectResponse("/integration?notice=Session+stopped.+Original+workload+restoration+requested.", status_code=303)

    @app.route("/integration/consent", methods=["POST"])
    async def image_consent(request):
        if not isinstance(pipeline.engine, RemoteInferenceEngine):
            raise ValueError("Select an authenticated worker before enabling image transmission")
        form = await request.form()
        busy()
        try:
            pipeline.engine.allow_remote = "allow" in form
            store.audit("remote_consent", "enabled" if pipeline.engine.allow_remote else "disabled")
        finally:
            pipeline.busy.release()
        return RedirectResponse("/integration?notice=Image+permission+updated", status_code=303)

    @app.route("/integration/engine", methods=["POST"])
    async def engine_edit(request):
        form = await request.form()
        if form.get("kind") == "mock":
            value = {"kind": "mock", "id": "synthetic-mock", "answers": {**settings.mock_answers, "human_present": False}}
            engine = MockInferenceEngine(value["answers"], value["id"])
        elif form.get("kind") == "worker":
            value = profile({"kind": "worker", "id": str(form["engine_id"]), "version": str(form["version"]), "worker_id": str(form["worker_id"]), "url": str(form["url"]), "secret_ref": str(form["secret_ref"]), "transport": str(form["transport"]), "synthetic": "synthetic" in form})
            key = str(form.get("worker_token", ""))
            if key:
                if not 32 <= len(key) <= 256 or not key.isascii() or any(c.isspace() for c in key):
                    raise ValueError("Worker key must be 32–256 ASCII characters without whitespace")
                await run_in_threadpool(secrets.set, value["secret_ref"], key)
            engine = RemoteInferenceEngine(value, allow_remote="remote_consent" in form, secrets=secrets)
        else:
            raise ValueError("Unknown engine kind")
        busy()
        try:
            with store.connection() as db:
                db.execute("INSERT OR REPLACE INTO release_settings VALUES('engine_profile',?)", (dumps(value),))
            if isinstance(engine, MockInferenceEngine):
                for sid, qid, version, preset in store.mock_values():
                    engine.configure_source_answer(sid, qid, version, preset)
            pipeline.engine, pipeline.engine_profile = engine, value
            store.audit("engine_selection", value["kind"])
        finally:
            pipeline.busy.release()
        return RedirectResponse("/integration?notice=Backend+selected", status_code=303)

    @app.route("/integration/health", methods=["POST"])
    async def engine_health(request):
        if isinstance(pipeline.engine, RemoteInferenceEngine):
            try:
                health = await run_in_threadpool(pipeline.engine.health)
            except ProviderError as exc:
                health = {"ready": False, "error": exc.code, "message": exc.message}
        else:
            health = {"ready": True, "device": "mock", "synthetic": True, "engine_id": pipeline.engine.engine_id}
        store.audit("engine_health", "ready" if health.get("ready") else "unavailable")
        return app.state.page("Worker health", request, [*worker_health_content(health), A("Return to setup", href="/integration")], view="settings")

    @app.route("/integration/camera", methods=["POST"])
    async def camera_edit(request):
        form = await request.form()
        sid = identifier(str(form["source_id"]))
        parsed = urlsplit(str(form["endpoint"]))
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
            if parsed.scheme not in ("rtsp", "rtsps") or not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.query or parsed.path not in ("/stream1", "/stream2") or parsed.port not in (None, 554):
                raise ValueError()
        except ValueError:
            raise ValueError("Use a literal private LAN camera IP, RTSP port 554, /stream1 or /stream2, without credentials") from None
        record = {"source_id": sid, "model": str(form["model"]), "endpoint_ref": sid + "-endpoint", "credentials_ref": sid + "-credentials", "allowed_hosts": [parsed.hostname]}
        source = camera_source(record)
        if store.is_removed(sid):
            raise ValueError("Restore this source on Sources before editing its camera setup")
        if sid in pipeline.sources and pipeline.sources[sid].kind != "rtsp":
            raise ValueError("Source ID already belongs to another input")
        if sid not in pipeline.sources and len(pipeline.sources) >= 32:
            raise ValueError("At most 32 sources")
        if sid in pipeline.sources and pipeline.sources[sid].settings.get("privacy_masks"):
            record["privacy_masks"] = pipeline.sources[sid].settings["privacy_masks"]
            source = replace(source, settings={**source.settings, "privacy_masks": record["privacy_masks"]})
        username, password = str(form.get("username", "")), str(form.get("password", ""))
        if password:
            if not 1 <= len(username) <= 128 or not 1 <= len(password) <= 128 or any(ord(c) < 32 for c in username + password):
                raise ValueError("Invalid camera account credentials")
            await run_in_threadpool(secrets.set, record["credentials_ref"], json.dumps({"username": username, "password": password}))
        else:
            await run_in_threadpool(secrets.camera, record["credentials_ref"])
        await run_in_threadpool(secrets.set, record["endpoint_ref"], str(form["endpoint"]))
        busy()
        try:
            store.configure(replace(settings, sources=(source,)))
            with store.connection() as db:
                db.execute("INSERT OR REPLACE INTO release_settings VALUES(?,?)", ("camera_profile:" + sid, dumps(record)))
            pipeline.sources[sid] = source
            store.audit("camera_setup", "saved_protected_references")
        finally:
            pipeline.busy.release()
        return RedirectResponse("/integration?camera=" + sid + "&notice=Camera+setup+saved", status_code=303)

    @app.route("/integration/cameras/{source_id}/test", methods=["POST"])
    async def camera_test(source_id: str, request):
        form = await request.form()
        if "capture_consent" not in form or source_id not in pipeline.sources or pipeline.sources[source_id].kind != "rtsp":
            raise ValueError("Explicit camera capture consent is required")
        busy()
        try:
            source = pipeline.sources[source_id]
            try:
                frame = await run_in_threadpool(SourceAdapters(allow_live_sources=True, timeout_seconds=settings.capture_timeout_seconds).capture, source)
                masked = await run_in_threadpool(preprocess, frame, source.settings.get("privacy_masks", []), preview=True)
                pipeline.latest_preview = (source_id, frame.frame_id, masked.payload)
                content = [P(f"Capture succeeded: {frame.width} × {frame.height}. No inference was requested; evidence was not retained."), evidence_image(f"/ui/preview/{source_id}/{frame.frame_id}", "Privacy-masked connection preview")]
                diagnostic = {"source_id": source_id, "status": "capture_success", "width": frame.width, "height": frame.height, "captured_at_utc": frame.captured_at_utc.isoformat()}
                store.audit("camera_connection_test", dumps(diagnostic))
            except ProviderError as exc:
                content = [P("Capture failed: " + exc.code), P("Check the camera account, LAN address and availability. You can save corrected credentials and retry.")]
                diagnostic = {"source_id": source_id, "status": exc.code}
                store.audit("camera_connection_test", dumps(diagnostic))
            with store.connection() as db:
                db.execute("INSERT OR REPLACE INTO release_settings VALUES(?,?)", ("camera_test:" + source_id, dumps(diagnostic)))
        finally:
            pipeline.busy.release()
        return app.state.page("Camera connection test", request, [*content, A("Return to setup", href="/integration")], view="sources")
