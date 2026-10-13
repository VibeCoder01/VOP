from dataclasses import replace
from io import BytesIO
import multiprocessing
import socket
import sys
from types import SimpleNamespace

from PIL import Image
import pytest

from vop.config import SourceSpec
from vop.contracts import ProviderError, Status
from vop.inputs import sources
from vop.inputs.file_image import FileImageAdapter


def spec(kind, settings=None):
    return SourceSpec("test-source", "Test source", kind, settings or {}, ())


def test_synthetic_and_file_adapters_have_portable_bytes(tmp_path):
    synthetic = sources.SourceAdapters().capture(spec("synthetic"))
    path = tmp_path / "scene.png"
    path.write_bytes(synthetic.payload)
    imported = sources.SourceAdapters().capture(spec("file", {"path": str(path)}))
    assert synthetic.source_id == imported.source_id == "test-source"
    assert synthetic.sha256 == imported.sha256 and synthetic.frame_id != imported.frame_id


@pytest.mark.parametrize("endpoint", ["http://elsewhere.example/image", "file:///private", "http://user:password@camera.example/image", "http://camera.example:bad/image", "http://camera.example/image#fragment", ""])
def test_endpoint_policy_rejects_before_connection(monkeypatch, endpoint):
    monkeypatch.setenv("TEST_CAMERA", endpoint)
    source = spec("snapshot", {"endpoint_env": "TEST_CAMERA", "allowed_hosts": ["camera.example"]})
    with pytest.raises(ProviderError) as exc:
        sources.camera_endpoint(source)
    assert exc.value.code == "endpoint_denied" and "password" not in str(exc.value)


@pytest.mark.parametrize("kind", ["usb", "rtsp", "snapshot"])
def test_live_source_never_opens_without_consent(kind):
    with pytest.raises(ProviderError) as exc:
        sources.SourceAdapters().capture(spec(kind))
    assert exc.value.code == "live_consent_required"


def test_mock_http_snapshot_request_bytes_and_redirect_policy(monkeypatch):
    frame = sources.capture_inline(spec("synthetic"))
    calls = []
    monkeypatch.setenv("TEST_CAMERA", "https://camera.example/snapshot?operator-secret=value")
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, maximum):
            assert maximum == sources.MAX_IMAGE_BYTES + 1
            return frame.payload
    class Opener:
        def open(self, request, *, timeout):
            calls.append((request.full_url, timeout))
            return Response()
    monkeypatch.setattr(sources, "build_opener", lambda *args: Opener())
    result = sources.capture_inline(spec("snapshot", {"endpoint_env": "TEST_CAMERA", "allowed_hosts": ["camera.example"]}), timeout=3)
    assert result.sha256 == frame.sha256 and calls[0][1] == 3
    with pytest.raises(ProviderError, match="redirect_denied"):
        sources.NoRedirect().redirect_request(None, None, 302, None, None, "https://elsewhere.example")


@pytest.mark.parametrize("opened,read_ok,encode_ok,expected", [(True, True, True, None),
                                                              (False, True, True, "capture_open_failed"),
                                                              (True, False, True, "capture_read_failed"),
                                                              (True, True, False, "capture_encode_failed")])
def test_usb_cv2_acquisition_and_release(monkeypatch, opened, read_ok, encode_ok, expected):
    payload = sources.capture_inline(spec("synthetic")).payload
    released = []
    capture = SimpleNamespace(isOpened=lambda: opened, read=lambda: (read_ok, object()), release=lambda: released.append(True))
    fake = SimpleNamespace(VideoCapture=lambda locator: capture,
                           imencode=lambda extension, image: (encode_ok, SimpleNamespace(tobytes=lambda: payload)))
    monkeypatch.setitem(sys.modules, "cv2", fake)
    if expected:
        with pytest.raises(ProviderError) as error:
            sources.capture_inline(spec("usb", {"device": 0}))
        assert error.value.code == expected
    else:
        frame = sources.capture_inline(spec("usb", {"device": 0}))
        assert frame.source_id == "test-source" and frame.captured_at_utc <= frame.received_at_utc
    assert released == [True]


def test_missing_camera_dependency_typed(monkeypatch):
    monkeypatch.setitem(sys.modules, "cv2", None)
    with pytest.raises(ProviderError) as error:
        sources.capture_inline(spec("usb", {"device": 0}))
    assert error.value.code == "dependency_missing"


def test_actual_spawned_capture_child_synthetic_only():
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(target=sources.capture_child, args=(send, spec("synthetic"), 5))
    process.start()
    send.close()
    try:
        assert receive.poll(10)
        frame = receive.recv()["frame"]
        assert frame.source_id == "test-source" and frame.payload.startswith(b"\x89PNG")
        process.join(5)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)
        receive.close()
        process.close()


def test_capture_hard_timeout_terminates_worker(monkeypatch):
    events = []
    class End:
        def close(self): pass
        def poll(self, timeout): return False
    class Child:
        pid = None
        alive = True
        def start(self): self.pid = 123
        def is_alive(self): return self.alive
        def terminate(self):
            events.append("terminate")
            self.alive = False
        def join(self, timeout): events.append("join")
        def close(self): events.append("close")
    context = SimpleNamespace(Pipe=lambda **kwargs: (End(), End()), Process=lambda **kwargs: Child())
    monkeypatch.setattr(sources.multiprocessing, "get_context", lambda name: context)
    with pytest.raises(ProviderError) as error:
        sources.SourceAdapters(allow_live_sources=True, timeout_seconds=0.01).capture(spec("usb", {"device": 0}))
    assert error.value.code == "capture_timeout" and error.value.status == Status.TIMEOUT
    assert events == ["terminate", "join", "close"]


def test_image_byte_limit_and_network_guard():
    with pytest.raises(ProviderError) as error:
        FileImageAdapter().from_bytes(b"x" * (sources.MAX_IMAGE_BYTES + 1))
    assert error.value.code == "image_too_large"
    with socket.socket() as sock:
        with pytest.raises(AssertionError, match="Network access"):
            sock.connect(("127.0.0.1", 1))
    with pytest.raises(AssertionError, match="Network access"):
        socket.create_connection(("example.com", 80))
