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
from vop.dashboard import field, hidden, evidence_image, dependency_panel, action
from vop.inference.liquid_d1 import CHECKPOINT_REVISION
from vop.inference.mock import MockInferenceEngine
from vop.inference.remote import RemoteInferenceEngine, profile
from vop.inputs.sources import SourceAdapters
from vop.preprocessing import preprocess
from vop.secrets import SecretStore, reference
from vop.storage import dumps
from vop.ui_readiness import camera_dependencies, worker_dependencies


def antec_profile(engine):
    return (isinstance(engine, RemoteInferenceEngine) and engine.config["worker_id"] == "antec-d1"
            and engine.config["transport"] == "ssh" and engine.config["url"] == "http://127.0.0.1:8878"
            and engine.engine_id == "liquid-d1-3b" and engine.engine_version == CHECKPOINT_REVISION and not engine.synthetic)


def worker_health_content(health):
    runtime = health.get("runtime") or {}
    if health.get("ready"):
        message = "Worker ready — " + ("synthetic mock" if health.get("synthetic") else str(runtime.get("gpu_name") or runtime.get("device") or "model loaded"))
    else:
        message = "Worker unavailable. Start an antec session below, or check your existing worker and tunnel."
    error = health.get('error') or ''
    code = error.get('code', '') if isinstance(error, dict) else str(error)
    guidance = {"gpu_capacity": "GPU memory is insufficient. Check antec's existing workload and retry the timed session.",
                "host_capacity": "The worker has insufficient free RAM for this model.",
                "secret_unavailable": "Save the worker access key in backend setup.",
                "worker_auth": "The worker rejected its key. Correct the saved worker access key.",
                "worker_identity": "The running worker does not match the selected identity/model. Correct the profile or worker.",
                "clock_skew": "Synchronise the laptop and worker clocks before retrying.",
                "worker_unavailable": "Start the worker and SSH tunnel, then test health again."}.get(code)
    return [P(message, role="status", cls="readiness success" if health.get("ready") else "readiness error"),
            P(guidance, cls="readiness warning") if guidance else None,
            P("Device: " + str(runtime.get("device", "not connected")) + " · Precision: " + str(runtime.get("precision") or "not reported")),
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
        elif session.get("ended"):
            session_message = "The last app-managed session ended. Start another session and test worker health before capture."
        session_problems = worker_dependencies(pipeline.engine)
        if not antec_profile(pipeline.engine):
            session_problems.append(("Select the real antec-d1 SSH backend at http://127.0.0.1:8878 first.", "#backend-setup"))
        import os, shutil
        if not shutil.which("ssh.exe" if os.name == "nt" else "ssh"):
            session_problems.append(("SSH is missing. Install OpenSSH or Git for Windows before starting an antec session.", "#connection"))
        cached_health = getattr(pipeline.engine, "last_health", None)
        content = [Section(H2("Selected inference backend"), P("Engine: " + pipeline.engine.engine_id), Details(Summary("Saved backend details"), Pre(dumps(current))),
                    P("Captures use this selected worker. Images are privacy-masked before transmission." if isinstance(pipeline.engine, RemoteInferenceEngine) else "Mock selected — synthetic answers only; no image understanding.", cls="readiness info"),
                    P("Worker profiles use a local loopback endpoint reached directly or through an SSH tunnel. Camera location and model location are independent.")),
                   Section(H2("Antec connection"), P(session_message, role="status", cls="readiness info" if session["active"] else "readiness warning"),
                    P("Start temporarily pauses antec's llama workload, starts a timed GPU session and SSH tunnel, then restores the workload at the end, on Stop, or when the connection closes."),
                    dependency_panel(session_problems, ready="Backend and local key are set. Start checks the tunnel port and trusted SSH login; model/GPU readiness is confirmed by Test worker health."),
                    Form(hidden(csrf), Select(*(Option(str(m) + " minutes", value=str(m)) for m in (15, 30, 60)), name="minutes", aria_label="Session duration"),
                         Button("Start antec session", disabled=session["active"] or bool(session_problems)), method="post", action="/integration/session/start"),
                    P("Stop is available only while this app owns an active session.", cls="muted"),
                    Form(hidden(csrf), Button("Stop session and restore workload", disabled=not session["active"], cls="danger"), method="post", action="/integration/session/stop"),
                    *(worker_health_content(cached_health) if cached_health else [P("Worker connection has not been checked in this app session. Starting a session does not prove the model is ready.", cls="readiness warning")]), id="connection"),
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
                    P("Selecting a worker enables image transmission to it. Starting a session or capturing remains a separate action."),
                    Button("Save and select backend"), method="post", action="/integration/engine"), id="backend-setup"),
                   Form(hidden(csrf), dependency_panel(worker_dependencies(pipeline.engine)) if worker_dependencies(pipeline.engine) else None,
                        Button("Test worker identity and health (no images)", disabled=bool(worker_dependencies(pipeline.engine))), method="post", action="/integration/health"),
                   Section(H2("Protected Tapo setup"), P("Credentials are protected locally and never saved in the configuration or audit. Saving does not connect or start sampling. A blank password preserves the existing camera credentials. Retry setup and connection tests as needed."),
                    P("Use a different source ID for each camera, such as tapo-c200 and tapo-c210. Reusing an ID updates that camera's setup."),
                    P(camera_notice),
                    *(P(A("Edit " + s.source_id, href="/integration?camera=" + s.source_id)) for s in saved_cams),
                    P(A("Add another camera", href="/integration?new_camera=1")),
                    Form(hidden(csrf), field("Camera ID (optional; generated automatically)", "source_id", selected.source_id if selected else "", placeholder="Leave blank for an automatic name", readonly=bool(selected)),
                         Select(*(Option(m, value=m, selected=m == model) for m in ("C200", "C210", "C510W")), name="model", aria_label="Camera model"),
                         field("Camera RTSP endpoint (LAN IP, no credentials)", "endpoint", endpoint, placeholder="rtsp://192.168.1.100:554/stream1", required=True),
                         field("Camera account username", "username", username, autocomplete="username"),
                         field("Camera account password (blank keeps saved credentials)", "password", type="password", autocomplete="new-password"),
                         Button("Save camera and check connection", name='connect', value='1'), method="post", action="/integration/camera"), id="camera-setup"),
                   Section(H2("Camera connection tests"),
                         *(Form(hidden(csrf), P(s.name + " · " + s.source_id),
                                dependency_panel(camera_dependencies(s), ready="Test captures one local preview; it does not use a worker or retain evidence. Camera reachability and password validity are checked on Test."),
                                Button("Test camera connection", disabled=bool(camera_dependencies(s))), method="post", action=f"/integration/cameras/{s.source_id}/test") for s in cams),
                         P("Connection tests work while a source is disabled. For inference, enable the source and at least one question in Sources / Questions. Use Start VOP.cmd to launch with live capture enabled."))]
        if getattr(pipeline, 'auto_worker', None):
            content = [Section(H2('Your cameras'), P('Saved setup is reused. Observe now handles the Antec connection and its timed GPU session for you.'),
                       P('Demo mode produces synthetic answers. Choose Antec once for real image analysis.', cls='readiness warning') if isinstance(pipeline.engine, MockInferenceEngine) else None,
                       action('Use Antec AI', '/integration/engine/antec', csrf) if isinstance(pipeline.engine, MockInferenceEngine) else None,
                       *(Section(H2(s.name), P(s.source_id), action('Observe now', f'/ui/sources/{s.source_id}/capture', csrf),
                                 A('Edit camera', href='/integration?camera=' + s.source_id, cls='button secondary')) for s in cams),
                       P('Add a camera once using its address and camera account. VOP keeps these protected on this computer.') if not cams else None),
                       Details(Summary('Add or edit a camera'), content[4], open=not cams or bool(selected_id) or 'new_camera' in request.query_params),
                       Details(Summary('Advanced connection settings and manual controls'), *content[:4], content[5], open=request.query_params.get('advanced') == '1')]
        return app.state.page("Engine and camera setup", request, content, view="settings", notice=request.query_params.get("notice"))

    @app.route('/integration/engine/antec', methods=['POST'])
    def antec_preset():
        value = profile({'kind': 'worker', 'id': 'liquid-d1-3b', 'version': CHECKPOINT_REVISION, 'worker_id': 'antec-d1',
                         'url': 'http://127.0.0.1:8878', 'transport': 'ssh', 'secret_ref': 'antec-worker', 'synthetic': False})
        busy()
        try:
            with store.connection() as db:
                db.execute("INSERT OR REPLACE INTO release_settings VALUES('engine_profile',?)", (dumps(value),))
            pipeline.engine = RemoteInferenceEngine(value, allow_remote=True, secrets=secrets)
            pipeline.engine_profile = value
            store.audit('engine_selection', 'antec_preset')
        finally:
            pipeline.busy.release()
        return RedirectResponse('/integration?notice=Antec+selected.+Observe+now+will+connect+automatically.', status_code=303)

    @app.route("/integration/session/start", methods=["POST"])
    async def session_start(request):
        form = await request.form()
        engine = pipeline.engine
        if not antec_profile(engine):
            raise ValueError("Select the real antec-d1 SSH backend at http://127.0.0.1:8878 before starting its session")
        if worker_dependencies(engine):
            raise ValueError("Save a readable worker access key in backend setup before starting antec")
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
            engine = RemoteInferenceEngine(value, allow_remote=True, secrets=secrets)
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
                if getattr(pipeline, 'auto_worker', None):
                    await run_in_threadpool(pipeline.auto_worker.ensure_ready)
                health = await run_in_threadpool(pipeline.engine.health)
            except ProviderError as exc:
                health = {"ready": False, "error": exc.code, "message": exc.message}
                pipeline.engine.last_health = health
        else:
            health = {"ready": True, "device": "mock", "synthetic": True, "engine_id": pipeline.engine.engine_id}
        store.audit("engine_health", "ready" if health.get("ready") else "unavailable")
        return app.state.page("Worker health", request, [*worker_health_content(health), A("Return to setup", href="/integration")], view="settings")

    @app.route("/integration/camera", methods=["POST"])
    async def camera_edit(request):
        form = await request.form()
        requested_id = str(form.get('source_id', '')).strip()
        if not requested_id:
            base = 'tapo-' + str(form['model']).lower()
            requested_id, number = base, 1
            while requested_id in pipeline.sources or requested_id in pipeline.removed_sources:
                number += 1
                requested_id = base + '-' + str(number)
        sid = identifier(requested_id)
        is_new = sid not in pipeline.sources
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
            if is_new and form.get('connect') == '1':
                store.update_source(sid, enabled=True, retain_evidence=False, sample_interval_seconds=0)
            store.audit("camera_setup", "saved_protected_references")
        finally:
            pipeline.busy.release()
        if form.get('connect') == '1':
            return await camera_test(sid, request)
        return RedirectResponse("/integration?camera=" + sid + "&notice=Camera+setup+saved", status_code=303)

    @app.route("/integration/cameras/{source_id}/test", methods=["POST"])
    async def camera_test(source_id: str, request):
        if source_id not in pipeline.sources or pipeline.sources[source_id].kind != "rtsp":
            raise ValueError("Choose a saved camera before testing its connection")
        busy()
        try:
            source = pipeline.sources[source_id]
            try:
                frame = await run_in_threadpool(SourceAdapters(allow_live_sources=True, timeout_seconds=settings.capture_timeout_seconds).capture, source)
                masked = await run_in_threadpool(preprocess, frame, source.settings.get("privacy_masks", []), preview=True)
                pipeline.latest_preview = (source_id, frame.frame_id, masked.payload)
                content = [P(f"Capture succeeded: {frame.width} × {frame.height}. No inference was requested; evidence was not retained.", cls="readiness success"), evidence_image(f"/ui/preview/{source_id}/{frame.frame_id}", "Privacy-masked connection preview")]
                diagnostic = {"source_id": source_id, "status": "capture_success", "width": frame.width, "height": frame.height, "captured_at_utc": frame.captured_at_utc.isoformat()}
                store.audit("camera_connection_test", dumps(diagnostic))
            except ProviderError as exc:
                from vop.operator_workflow import recovery_message
                content = [P('The camera could not connect yet.', cls='readiness warning'), P(recovery_message(exc.code)),
                           action('Retry camera connection', f'/integration/cameras/{source_id}/test', request.scope['session']['csrf']),
                           A('Correct camera details', href='/integration?camera=' + source_id, cls='button secondary'),
                           Details(Summary('Technical details'), Pre(exc.code))]
                diagnostic = {"source_id": source_id, "status": exc.code}
                store.audit("camera_connection_test", dumps(diagnostic))
            with store.connection() as db:
                db.execute("INSERT OR REPLACE INTO release_settings VALUES(?,?)", ("camera_test:" + source_id, dumps(diagnostic)))
        finally:
            pipeline.busy.release()
        return app.state.page("Camera connection test", request, [*content, A("Return to setup", href="/integration")], view="sources")
