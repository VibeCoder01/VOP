from collections import deque
from io import BytesIO
from time import monotonic, sleep
from types import SimpleNamespace
from threading import Event
import sys

from PIL import Image
import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, VIEWER
from vop.live_preview import LivePreviews, MAX_CAMERAS, encode_preview, preview_child


class Worker:
    def __init__(self, source):
        self.source, self.frames, self.closed = source, deque(), False

    def poll(self):
        return self.frames.popleft() if self.frames else None

    def close(self):
        self.closed = True


def test_decoder_opens_once_drains_frames_and_masks_every_publication(monkeypatch):
    messages, opened = [], []
    two_frames = Event()
    deadline = monotonic() + 5
    class Pixels:
        def __getitem__(self, key): return self
    class Capture:
        released, reads = False, 0
        def __init__(self, *args): opened.append(self)
        def set(self, *args): pass
        def isOpened(self): return True
        def read(self):
            assert monotonic() < deadline, 'Synthetic decoder did not publish'
            sleep(.002)
            self.reads += 1
            return (False, None) if two_frames.is_set() else (True, Pixels())
        def release(self): self.released = True
    class Connection:
        def send(self, message):
            messages.append(message)
            if sum('frame' in item for item in messages) >= 2: two_frames.set()
        def close(self): pass
    monkeypatch.setitem(sys.modules, 'cv2', SimpleNamespace(VideoCapture=Capture, CAP_PROP_BUFFERSIZE=38))
    monkeypatch.setattr('vop.live_preview.os.dup2', lambda *_: None)
    monkeypatch.setattr('vop.live_preview.Image.fromarray', lambda *_: Image.new('RGB', (1280, 720), 'white'))
    source = SimpleNamespace(kind='usb', settings={'device': 0, 'privacy_masks': [[0, 0, .5, 1]]})
    preview_child(Connection(), source)
    frames = [m['frame'] for m in messages if 'frame' in m]
    assert len(opened) == 1 and opened[0].released
    assert len(frames) >= 2 and opened[0].reads > len(frames)
    for _, payload, _ in frames:
        with Image.open(BytesIO(payload)) as image:
            assert image.size == (960, 540) and image.getpixel((10, 10)) == (0, 0, 0)


def test_preview_timeout_retry_lease_expiry_and_configuration_change():
    source = SimpleNamespace(source_id='camera', kind='usb', settings={'device': 0})
    pipeline = SimpleNamespace(sources={'camera': source}, stopping=False)
    made = []
    def factory(source):
        made.append(Worker(source))
        return made[-1]
    previews = LivePreviews(pipeline, allowed=True, factory=factory)
    previews.leases['camera'] = 100
    previews.tick(0)
    made[-1].frames.append(('first', b'synthetic-image', '2026-10-22T00:00:00+00:00'))
    previews.tick(1)
    assert previews.image('camera')[0] == 'first'
    previews.tick(12)
    assert made[0].closed and previews.errors['camera'] == 'preview_timeout'
    previews.tick(13)
    assert len(made) == 1
    previews.tick(14)
    assert len(made) == 2
    made[-1].frames.append(('second', b'synthetic-image-2', '2026-10-22T00:00:01+00:00'))
    previews.tick(15)
    assert previews.image('camera')[0] == 'second' and not previews.errors
    pipeline.sources['camera'] = SimpleNamespace(source_id='camera', kind='usb', settings={'device': 1})
    previews.tick(16)
    assert made[1].closed and made[-1].source is pipeline.sources['camera']
    previews.tick(101)
    assert made[-1].closed and not previews.workers and not previews.leases
    assert previews.image('camera')[0] == 'second'  # Last image remains available after viewing stops.
    pipeline.sources.clear()
    previews.tick(102)
    assert not previews.images and not previews.progress
    previews.stop()


def test_camera_limit_coalescing_and_stop():
    sources = {str(i): SimpleNamespace(source_id=str(i), kind='usb', settings={'device': i}) for i in range(MAX_CAMERAS + 1)}
    previews = LivePreviews(SimpleNamespace(sources=sources, stopping=False), allowed=True, factory=Worker)
    previews.leases.update({sid: 100 for sid in sources})
    previews.tick(1)
    assert len(previews.workers) == MAX_CAMERAS
    assert previews.errors[str(MAX_CAMERAS)] == 'preview_capacity'
    old = dict(previews.workers)
    previews.tick(2)
    assert previews.workers == old
    previews.clear('0')
    assert old['0'].closed
    previews.tick(3)
    assert str(MAX_CAMERAS) in previews.workers
    previews.stop()
    assert all(w.closed for w in old.values())
    assert not previews.workers and not previews.images


def test_usb_observation_gets_exclusive_device_then_preview_resumes():
    source = SimpleNamespace(source_id='usb-camera', kind='usb', settings={'device': 0})
    previews = LivePreviews(SimpleNamespace(sources={source.source_id: source}, stopping=False), allowed=True, factory=Worker)
    previews.leases[source.source_id] = 100
    previews.tick(1)
    old = previews.workers[source.source_id]
    def capture(camera):
        assert camera is source and old.closed
        previews.tick(2)
        assert not previews.workers
        return 'explicit fixture frame'
    assert previews.capture(source, capture) == 'explicit fixture frame'
    previews.tick(3)
    assert previews.workers[source.source_id] is not old
    previews.stop()


def test_visible_preview_is_authorized_independent_and_does_not_record_answers(app, monkeypatch):
    from vop.browser_auth import BrowserAuth
    pipeline = app.state.pipeline
    made = []
    payload = encode_preview(Image.new('RGB', (1920, 1080), 'white'), [[0, 0, .5, 1]])
    image = Image.open(BytesIO(payload))
    assert image.size == (960, 540) and image.getpixel((10, 10)) == (0, 0, 0)
    def factory(source):
        worker = Worker(source)
        worker.frames.append(('fixture-live', payload, '2026-10-22T10:00:00+00:00'))
        made.append(worker)
        return worker
    def fail(*_):
        pytest.fail('Preview must not call observation capture or inference')
    monkeypatch.setattr(pipeline.capture_adapter, 'capture', fail)
    monkeypatch.setattr(pipeline.engine, 'infer', fail)
    pipeline.live_previews.factory = factory
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/integration/camera', data={'csrf': csrf, 'source_id': 'tapo-c200', 'model': 'C200',
            'endpoint': 'rtsp://192.168.1.100:554/stream1', 'username': 'fixture', 'password': 'fixture'})
        url = '/ui/live-preview/tapo-c200/keepalive'
        assert client.post(url, data={'csrf': csrf}).status_code == 422  # Live capture stays opt-in.
        pipeline.live_previews.allowed = True
        control = app.state.store.source_control('tapo-c200')
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        assert client.post(url, data={'csrf': 'wrong'}).status_code == 403
        assert client.post(url, data={'csrf': csrf}, headers={'Origin': 'http://other.test'}).status_code == 403
        assert client.post(url, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        assert client.get('/ui/live-preview/tapo-c200').status_code == 404 and not made
        middleware = app.middleware_stack
        while not isinstance(middleware, BrowserAuth):
            middleware = middleware.app
        middleware.admission.acquire()
        pipeline.busy.acquire()
        try:
            assert client.post(url, data={'csrf': csrf}).status_code == 202
            deadline = monotonic() + 3
            while not made or not pipeline.live_previews.image('tapo-c200'):
                assert monotonic() < deadline
                sleep(.01)
            assert client.post(url, data={'csrf': csrf}).status_code == 202
            assert len(made) == 1  # Multiple tabs share one decoder per camera.
            response = client.get('/ui/live-preview/tapo-c200')
            assert response.headers['content-type'].startswith('image/jpeg')
            assert response.headers['x-vop-preview-kind'] == 'live'
            assert response.headers['x-vop-monitoring'] == 'false'
            assert response.content == payload
            assert app.state.store.source_control('tapo-c200') == control
            assert app.state.store.health()['observation_count'] == 0
            assert app.state.store.latest_evidence('tapo-c200') is None
        finally:
            pipeline.busy.release()
            middleware.admission.release()
    assert made[0].closed
