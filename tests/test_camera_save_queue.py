from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login
from vop.browser_auth import BrowserAuth
from vop.contracts import ProviderError
from vop.inputs.sources import SourceAdapters


class ObservedLock:
    """Expose a real blocking wait so concurrency assertions need no sleeps."""
    def __init__(self):
        self.lock = Lock()
        self.waiting = Event()

    def acquire(self, blocking=True):
        if blocking and self.lock.locked():
            self.waiting.set()
        return self.lock.acquire(blocking)

    def release(self):
        self.lock.release()

    def locked(self):
        return self.lock.locked()


@pytest.mark.parametrize('route', ['/cameras/save', '/integration/camera'])
@pytest.mark.parametrize('editing', [False, True])
def test_camera_save_waits_without_partial_changes_or_blocking_ui(app, monkeypatch, route, editing):
    with TestClient(app) as client:
        csrf = login(client)
        app.state.sampler.stop()
        body = {'csrf': csrf, 'source_id': 'tapo-c200', 'model': 'C200', 'name': 'New camera',
                'endpoint': 'rtsp://192.168.1.100:554/stream1', 'username': 'offline-fixture', 'password': 'offline-fixture'}
        if editing:
            assert client.post(route, data=body).status_code == 200
            body.update(name='Updated camera', endpoint='rtsp://192.168.1.101:554/stream1')
        controls = app.state.store.source_control('synthetic-scene')
        count = app.state.store.health()['observation_count']
        middleware = app.middleware_stack
        while not isinstance(middleware, BrowserAuth):
            middleware = middleware.app
        admission, busy = ObservedLock(), ObservedLock()
        monkeypatch.setattr(middleware, 'admission', admission)
        monkeypatch.setattr(app.state.pipeline, 'busy', busy)
        writes = []
        original_set = app.state.secrets.set
        def save(name, value):
            writes.append(name)
            return original_set(name, value)
        monkeypatch.setattr(app.state.secrets, 'set', save)
        monkeypatch.setattr(SourceAdapters, 'capture', lambda *_: pytest.fail('Saving must not open a camera'))
        admission.acquire()
        busy.acquire()
        admission_held = True
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.post, route, data=body)
            try:
                assert admission.waiting.wait(3), 'Save must wait for request admission'
                assert not pending.done() and not writes
                admission.release()
                admission_held = False
                assert busy.waiting.wait(3), 'Save must wait for the observation'
                assert not pending.done() and not writes
                assert client.get('/api/v1/health').status_code == 200
                assert app.state.store.source_control('synthetic-scene') == controls
                if editing:
                    assert app.state.pipeline.sources['tapo-c200'].name == 'New camera'
                    assert app.state.secrets.get('tapo-c200-endpoint').endswith('.100:554/stream1')
                else:
                    assert 'tapo-c200' not in app.state.pipeline.sources
            finally:
                if admission_held:
                    admission.release()
                busy.release()
            response = pending.result(timeout=5)
        assert response.status_code == 200 and 'overloaded' not in response.text
        assert app.state.secrets.get('tapo-c200-endpoint') == body['endpoint']
        assert app.state.pipeline.sources['tapo-c200'].name == body['name']
        assert not busy.locked() and not admission.locked()
        assert app.state.store.health()['observation_count'] == count
        assert app.state.store.source_control('synthetic-scene') == controls


def test_failed_protected_camera_write_releases_locks_and_can_retry(app, monkeypatch):
    with TestClient(app) as client:
        csrf = login(client)
        app.state.sampler.stop()
        body = {'csrf': csrf, 'source_id': 'tapo-c200', 'model': 'C200',
                'endpoint': 'rtsp://192.168.1.100:554/stream1', 'username': 'offline-fixture', 'password': 'offline-fixture'}
        with monkeypatch.context() as patch:
            def fail(*_):
                raise ProviderError('secret_unavailable', 'Synthetic protected storage failure')
            patch.setattr(app.state.secrets, 'set', fail)
            response = client.post('/cameras/save', data=body)
        assert response.status_code == 422
        assert 'tapo-c200' not in app.state.pipeline.sources
        assert not app.state.pipeline.busy.locked()
        assert client.post('/cameras/save', data=body).status_code == 200
