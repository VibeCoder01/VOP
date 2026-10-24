"""Local prerequisites for operator actions; rendering never opens cameras or workers."""
from importlib.util import find_spec
from pathlib import Path

from vop.contracts import ProviderError
from vop.inference.mock import MockInferenceEngine
from vop.inference.remote import RemoteInferenceEngine
from vop.inputs.sources import camera_endpoint
from vop.secrets import SecretStore


def camera_dependencies(source):
    problems = []
    if source.kind in ("rtsp", "usb") and find_spec("cv2") is None:
        problems.append(("OpenCV is missing. Install the camera extra: python -m pip install '.[camera]'", "/cameras"))
    if source.kind in ("rtsp", "snapshot"):
        try:
            camera_endpoint(source)
            if source.settings.get("secret_ref"):
                SecretStore().camera(source.settings["secret_ref"])
        except ProviderError as exc:
            message = ("The saved camera address does not match its allowed address. Edit the camera address and save it again."
                       if exc.code == "endpoint_denied" else
                       "Saved camera details are unavailable. Open camera setup to check the address and camera account. Any readable saved details are kept.")
            problems.append((message, "/cameras/" + source.source_id if source.settings.get("endpoint_secret_ref") else "/cameras"))
    if source.kind == "file" and not Path(source.settings["path"]).is_file():
        problems.append(("The configured image file is missing. Correct its path in the source configuration.", "/?view=sources"))
    return problems


def worker_dependencies(engine):
    if not isinstance(engine, RemoteInferenceEngine):
        return []
    try:
        key = engine.secrets.get(engine.config["secret_ref"])
        if not 32 <= len(key) <= 256 or not key.isascii() or any(c.isspace() for c in key):
            raise ProviderError("secret_unavailable", "Invalid worker key")
    except ProviderError:
        return [("Worker access key is unavailable. Save the protected key in backend setup.", "/engines")]
    return []


def capture_dependencies(pipeline, source_id):
    source = pipeline.sources[source_id]
    problems = []
    if not pipeline.store.source_control(source_id)["enabled"]:
        problems.append(("Source is disabled. Enable it in Source controls.", f"/ui/sources/{source_id}"))
    questions = pipeline.store.questions(source_id, active_only=True)
    if not questions:
        problems.append(("No enabled questions. Add or enable a question first.", "/?view=questions&source=" + source_id))
    if any(q['spec'].kind not in pipeline.engine.capabilities() for q in questions):
        problems.append(("The selected backend does not support an enabled question type. Change the question or choose a compatible backend.", "/?view=questions&source=" + source_id))
    if source.kind not in ("synthetic", "file") and not getattr(pipeline.capture_adapter, "allow_live_sources", True):
        problems.append(("Camera access is off. Close VOP and reopen Start VOP.", "/cameras"))
    problems.extend(camera_dependencies(source))
    automatic = getattr(pipeline, 'auto_worker', None)
    from vop.operator_workflow import is_antec
    automatic = automatic and is_antec(pipeline.engine)
    if not automatic:
        problems.extend(worker_dependencies(pipeline.engine))
    if isinstance(pipeline.engine, MockInferenceEngine):
        if any(q['spec'].question_id not in pipeline.engine.configured and (source_id, q['spec'].question_id, q['spec'].version) not in pipeline.engine.source_answers for q in questions):
            problems.append(("Mock answers are missing. Save a synthetic answer in Questions or select a real worker.", "/?view=questions&source=" + source_id))
    else:
        health = getattr(pipeline.engine, "last_health", None)
        if not automatic and health is not None and not health.get("ready"):
            problems.append(("Worker was unavailable at the last check. Start/check the worker and SSH tunnel, then test worker health again.", "/engines"))
    return problems
