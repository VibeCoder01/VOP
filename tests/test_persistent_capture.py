"""Synthetic persistent acquisition contracts; no camera, credential or model access."""
from io import BytesIO
from types import SimpleNamespace
import sys

from PIL import Image
import pytest

from vop.contracts import ProviderError
from vop.inputs.persistent import PersistentCameras, camera_child, MAX_CONNECTIONS


def source(sid='camera', **settings):
    return SimpleNamespace(source_id=sid, kind='rtsp', sample_interval_seconds=1, settings=settings)


class Worker:
    def __init__(self, source):
        self.closed, self.calls, self.fail = False, 0, False

    def capture(self, timeout):
        assert not self.closed
        self.calls += 1
        if self.fail:
            raise ProviderError('capture_timeout', 'Synthetic timeout')
        return self.calls

    def close(self):
        self.closed = True

    def alive(self):
        return not self.closed


def test_reuse_opt_out_capacity_pause_edit_delete_and_shutdown(monkeypatch):
    monkeypatch.setattr('vop.inputs.persistent.camera_endpoint', lambda source: None)
    controls = {'enabled': True, 'sample_interval_seconds': 1}
    store = SimpleNamespace(source_control=lambda sid: controls, questions=lambda *a, **kw: [1])
    sources = {str(n): source(str(n)) for n in range(MAX_CONNECTIONS + 1)}
    pipeline = SimpleNamespace(sources=sources, stopping=False, store=store,
                               settings=SimpleNamespace(capture_timeout_seconds=2))
    pool = PersistentCameras(pipeline, allowed=True, factory=Worker)
    once = lambda s: 'one-shot'
    try:
        first = sources['0']
        assert pool.capture(first, once) == 1
        worker = pool.workers['0'][1]
        assert pool.capture(first, once) == 2 and pool.workers['0'][1] is worker
        for sid in list(sources)[1:MAX_CONNECTIONS]: pool.capture(sources[sid], once)
        assert pool.capture(sources[str(MAX_CONNECTIONS)], once) == 'one-shot'
        controls['sample_interval_seconds'] = 0
        pool.tick()
        assert not pool.workers and worker.closed
        controls['sample_interval_seconds'] = 1
        pool.capture(first, once)
        worker = pool.workers['0'][1]
        sources['0'] = source('0', persistent_capture=False)
        pool.tick()
        assert worker.closed and pool.capture(sources['0'], once) == 'one-shot'
        sources['0'] = source('0')
        pool.capture(sources['0'], once)
        worker = pool.workers['0'][1]
        worker.fail = True
        with pytest.raises(ProviderError, match='capture_timeout'): pool.capture(sources['0'], once)
        assert worker.closed and '0' not in pool.workers
        assert pool.capture(sources['0'], once) == 1  # Reconnect on the next request.
        worker = pool.workers['0'][1]
        del sources['0']
        pool.tick()
        assert worker.closed and not pool.workers
        pool.capture(sources['1'], once)
    finally:
        pool.stop()
    assert not pool.workers and not pool.thread.is_alive()
    denied = PersistentCameras(pipeline, allowed=False, factory=lambda s: pytest.fail('No consent'))
    assert denied.capture(sources['1'], once) == 'one-shot'


def test_child_opens_once_drains_and_reads_after_each_request(monkeypatch):
    buffer = BytesIO()
    Image.new('RGB', (10, 8), 'white').save(buffer, format='PNG')
    opened, sent, order = [], [], []
    class Encoded:
        def tobytes(self): return buffer.getvalue()
    class Capture:
        def __init__(self, *a): opened.append(self)
        def set(self, *a): pass
        def isOpened(self): return True
        def grab(self): order.append('grab'); return True
        def retrieve(self): order.append('retrieve'); return True, 'synthetic-pixels'
        def release(self): order.append('release')
    class Connection:
        calls = 0
        def poll(self):
            self.calls += 1
            return self.calls in (2, 4, 5)
        def recv(self):
            order.append('request')
            return 'capture' if self.calls < 5 else 'stop'
        def send(self, item): sent.append(item); order.append('response')
        def close(self): pass
    monkeypatch.setitem(sys.modules, 'cv2', SimpleNamespace(VideoCapture=Capture, CAP_FFMPEG=1,
        CAP_PROP_OPEN_TIMEOUT_MSEC=2, CAP_PROP_READ_TIMEOUT_MSEC=3, CAP_PROP_BUFFERSIZE=4,
        imencode=lambda *a: (True, Encoded())))
    monkeypatch.setattr('vop.inputs.persistent.os.dup2', lambda *a: None)
    monkeypatch.setattr('vop.inputs.persistent.camera_locator', lambda source: 'synthetic')
    camera_child(Connection(), source())
    assert len(opened) == 1 and len(sent) == 2
    assert order == ['grab', 'request', 'grab', 'retrieve', 'response', 'grab', 'request', 'grab', 'retrieve', 'response', 'request', 'release']
    frames = [item['frame'] for item in sent]
    assert frames[0].frame_id != frames[1].frame_id
    assert all((frame.width, frame.height) == (10, 8) for frame in frames)
    assert frames[1].captured_at_utc >= frames[0].captured_at_utc
