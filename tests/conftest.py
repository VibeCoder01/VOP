"""Every test denies network connections, including accidental model downloads."""
from pathlib import Path
import socket
from threading import local

import pytest

from vop.contracts import InferenceRequest
from vop.examples import questions
from vop.inputs.file_image import FileImageAdapter


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original_connect, original_pair = socket.socket.connect, socket.socketpair
    internal = local()
    def connect(sock, address):
        # Windows implements asyncio's internal wake-up socketpair with a loopback connect.
        # Permit only that stdlib operation on this thread, never HTTP/camera/model traffic.
        if getattr(internal, "socketpair", False) and isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        raise AssertionError("Network access is forbidden in offline tests")
    def pair(*args, **kwargs):
        internal.socketpair = True
        try:
            return original_pair(*args, **kwargs)
        finally:
            internal.socketpair = False
    def deny(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline tests")
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "socketpair", pair)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


@pytest.fixture
def request_frame():
    frame = FileImageAdapter().read(Path(__file__).resolve().parents[1] / "fixtures" / "scene.png")
    return InferenceRequest(frame, questions()[:3])
