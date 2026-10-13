"""One-shot acquisition. Live adapters run in a killable child, never on import."""
from dataclasses import replace
from io import BytesIO
import multiprocessing
import os
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from PIL import Image, ImageDraw

from vop.config import SourceSpec
from vop.contracts import FrameEnvelope, ProviderError, Status, utcnow
from vop.inputs.file_image import FileImageAdapter

MAX_IMAGE_BYTES = 20 * 1024 * 1024


class FrameSource(Protocol):
    def capture(self, source: SourceSpec) -> FrameEnvelope: ...


def camera_endpoint(source: SourceSpec) -> str:
    endpoint = os.environ.get(source.settings["endpoint_env"], "")
    try:
        parsed = urlsplit(endpoint)
        allowed_schemes = ("rtsp", "rtsps") if source.kind == "rtsp" else ("http", "https")
        if (parsed.scheme not in allowed_schemes or not parsed.hostname or parsed.fragment
            or parsed.username is not None or parsed.password is not None
            or parsed.hostname.lower() not in {h.lower() for h in source.settings["allowed_hosts"]}):
            raise ValueError("Denied endpoint")
        parsed.port  # validate malformed ports before any connection
    except ValueError as exc:
        raise ProviderError("endpoint_denied", "Endpoint is missing, malformed or outside source policy") from exc
    return endpoint


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("redirect_denied", "Snapshot redirects are disabled")


def capture_inline(source: SourceSpec, timeout: float = 10) -> FrameEnvelope:
    adapter = FileImageAdapter()
    if source.kind == "file":
        return adapter.read(source.settings["path"], source.source_id)
    if source.kind == "synthetic":
        image = Image.new("RGB", (384, 256), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((50, 70, 150, 170), fill="red")
        draw.ellipse((220, 70, 320, 170), fill="blue")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return adapter.from_bytes(buffer.getvalue(), source.source_id)
    if source.kind == "snapshot":
        endpoint = camera_endpoint(source)
        # No inherited system proxy or credential handling; endpoint is operator-owned.
        opener = build_opener(NoRedirect(), ProxyHandler({}))
        try:
            with opener.open(Request(endpoint, headers={"Accept": "image/jpeg,image/png"}), timeout=timeout) as response:
                payload = response.read(MAX_IMAGE_BYTES + 1)
        except (HTTPError, URLError, OSError) as exc:
            raise ProviderError("snapshot_failed", "Snapshot acquisition failed") from exc
        return adapter.from_bytes(payload, source.source_id)
    if source.kind in ("usb", "rtsp"):
        locator = source.settings["device"] if source.kind == "usb" else camera_endpoint(source)
        try:
            import cv2
        except ImportError as exc:
            raise ProviderError("dependency_missing", "Install the optional OpenCV camera dependency") from exc
        capture = cv2.VideoCapture(locator)
        try:
            if not capture.isOpened():
                raise ProviderError("capture_open_failed", "Camera could not be opened")
            ok, pixels = capture.read()
            if not ok or pixels is None:
                raise ProviderError("capture_read_failed", "Camera returned no frame")
            stamp = utcnow()
            ok, encoded = cv2.imencode(".png", pixels)
            if not ok:
                raise ProviderError("capture_encode_failed", "Camera image could not be encoded")
            frame = adapter.from_bytes(encoded.tobytes(), source.source_id)
            return replace(frame, captured_at_utc=stamp)
        finally:
            capture.release()
    raise ProviderError("source_unsupported", "Unsupported source adapter", Status.UNSUPPORTED)


def capture_child(connection, source: SourceSpec, timeout: float) -> None:
    # OpenCV/FFmpeg may include camera URLs in native diagnostics; suppress those entirely.
    with open(os.devnull, "w") as quiet:
        os.dup2(quiet.fileno(), 1)
        os.dup2(quiet.fileno(), 2)
        try:
            connection.send({"frame": capture_inline(source, timeout)})
        except ProviderError as exc:
            connection.send({"error": {"code": exc.code, "status": str(exc.status)}})
        except Exception:
            connection.send({"error": {"code": "capture_failed", "status": str(Status.MODEL_FAILURE)}})
        finally:
            connection.close()


class SourceAdapters:
    def __init__(self, *, allow_live_sources: bool = False, timeout_seconds: float = 10):
        self.allow_live_sources = allow_live_sources
        self.timeout_seconds = timeout_seconds

    def capture(self, source: SourceSpec) -> FrameEnvelope:
        if source.kind in ("synthetic", "file"):
            return capture_inline(source, self.timeout_seconds)
        if not self.allow_live_sources:
            raise ProviderError("live_consent_required", "Live source acquisition requires explicit operator consent")
        if source.kind in ("rtsp", "snapshot"):
            camera_endpoint(source)  # enforce policy before starting any child
        context = multiprocessing.get_context("spawn")
        receive, send = context.Pipe(duplex=False)
        process = context.Process(target=capture_child, args=(send, source, self.timeout_seconds), daemon=True)
        try:
            process.start()
            send.close()
            if not receive.poll(self.timeout_seconds):
                raise ProviderError("capture_timeout", "Capture exceeded its deadline", Status.TIMEOUT)
            try:
                message = receive.recv()
            except EOFError as exc:
                raise ProviderError("capture_failed", "Capture worker exited without a frame") from exc
            if "error" in message:
                raise ProviderError(message["error"]["code"], "Capture failed", Status(message["error"]["status"]))
            return message["frame"]
        finally:
            if process.pid:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=3)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=3)
                process.close()
            receive.close()
            send.close()
