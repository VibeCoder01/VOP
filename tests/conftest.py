"""Every test denies network connections, including accidental model downloads."""
from pathlib import Path
import socket

import pytest

from vop.contracts import InferenceRequest
from vop.examples import questions
from vop.inputs.file_image import FileImageAdapter


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline tests")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")


@pytest.fixture
def request_frame():
    frame = FileImageAdapter().read(Path(__file__).resolve().parents[1] / "fixtures" / "scene.png")
    return InferenceRequest(frame, questions()[:3])
