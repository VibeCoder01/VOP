"""Camera setup and engine profiles remain independent; no real hardware or secrets."""
from copy import deepcopy
import re

import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER
from vop.inference.liquid_d1 import CHECKPOINT_REVISION
from vop.inference.remote import RemoteInferenceEngine
from vop.service import create_app


def worker(csrf, **changes):
    return {'csrf': csrf, 'name': 'Antec AI', 'kind': 'worker', 'engine_id': 'liquid-d1-3b',
            'version': CHECKPOINT_REVISION, 'worker_id': 'antec-d1', 'url': 'http://127.0.0.1:8878',
            'transport': 'ssh', **changes}


def test_pages_separate_camera_and_engine_forms_and_read_only_visits(app, monkeypatch):
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', lambda *_: pytest.fail('GET must not capture'))
    with TestClient(app) as client:
        login(client)
        camera = client.get('/cameras/new')
        engine = client.get('/engines/new')
        assert camera.status_code == engine.status_code == 200
        assert 'name="endpoint"' in camera.text and 'name="worker_id"' not in camera.text
        assert 'name="worker_id"' in engine.text and 'name="endpoint"' not in engine.text
        assert 'name="password"' not in engine.text
        assert 'aria-current="page"' in camera.text
        assert 'Engine and camera setup' not in camera.text
        assert client.get('/engines/new?kind=mock').status_code == 200
        assert app.state.store.health()['observation_count'] == 0


def test_engine_save_edit_use_and_restart_do_not_modify_camera(app):
    with TestClient(app) as client:
        csrf = login(client)
        original = deepcopy(app.state.pipeline.engine_profile)
        sources = deepcopy(app.state.pipeline.sources)
        saved = client.post('/engines/new/save', data=worker(csrf))
        assert saved.status_code == 200 and saved.url.path == '/engines/antec-ai'
        assert app.state.pipeline.engine_profile == original
        assert 'Use engine' in saved.text and 'name="endpoint"' not in saved.text
        assert client.post('/engines/antec-ai/use', data={'csrf': csrf}).status_code == 200
        assert isinstance(app.state.pipeline.engine, RemoteInferenceEngine)
        active = deepcopy(app.state.pipeline.engine_profile)
        assert client.post('/engines/antec-ai/save', data=worker(csrf, name='Updated', worker_id='another-worker')).status_code == 200
        assert app.state.pipeline.engine_profile == active
        assert app.state.pipeline.sources == sources
        restarted = create_app(app.state.pipeline.settings, token=OWNER)
        assert restarted.state.pipeline.engine_profile == active
        with TestClient(restarted, headers={'Authorization': 'Bearer ' + OWNER}) as other:
            page = other.get('/engines/antec-ai').text
            assert 'Updated' in page and 'Use engine' in page
        assert client.post('/engines/antec-ai/use', data={'csrf': csrf}).status_code == 200
        assert app.state.pipeline.engine_profile['worker_id'] == 'another-worker'


def test_camera_save_does_not_capture_or_change_engine(app, monkeypatch):
    monkeypatch.setattr('vop.inputs.sources.SourceAdapters.capture', lambda *_: pytest.fail('Save must not capture'))
    with TestClient(app) as client:
        csrf = login(client)
        engine = app.state.pipeline.engine
        response = client.post('/cameras/save', data={'csrf': csrf, 'model': 'C210', 'endpoint': 'rtsp://192.168.1.210:554/stream1',
                                                    'username': 'fixture-user', 'password': 'fixture-password'})
        assert response.status_code == 200 and response.url.path == '/cameras/tapo-c210'
        assert app.state.pipeline.engine is engine
        assert app.state.store.source_control('tapo-c210')['sample_interval_seconds'] == 0
        edit = client.get('/cameras/tapo-c210/edit').text
        assert 'fixture-password' not in edit and 'fixture-user' in edit
        assert app.state.store.health()['observation_count'] == 0


def test_key_edit_does_not_replace_active_key_and_use_respects_busy(app):
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/engines/new/save', data=worker(csrf, worker_token='a' * 40))
        client.post('/engines/antec-ai/use', data={'csrf': csrf})
        active_ref = app.state.pipeline.engine_profile['secret_ref']
        client.post('/engines/antec-ai/save', data=worker(csrf, worker_token='b' * 40))
        assert app.state.secrets.get(active_ref) == 'a' * 40
        assert app.state.pipeline.engine.secrets.get(active_ref) == 'a' * 40
        app.state.pipeline.busy.acquire()
        try:
            assert client.post('/engines/antec-ai/use', data={'csrf': csrf}).status_code == 429
        finally: app.state.pipeline.busy.release()


def test_setup_permissions_csrf_and_generated_profile_names(app):
    with TestClient(app) as client:
        for path in ('/cameras', '/cameras/new', '/engines', '/engines/new', '/engines/current/edit'):
            assert client.get(path, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        csrf = login(client)
        assert client.post('/engines/new/save', data=worker('wrong')).status_code == 403
        assert client.post('/engines/new/save', data=worker(csrf)).url.path == '/engines/antec-ai'
        assert client.post('/engines/new/save', data=worker(csrf)).url.path == '/engines/antec-ai-2'
        assert client.post('/engines/new/save', data=worker(csrf, url='http://192.168.1.10:8878')).status_code == 400
        assert client.get('/engines/missing/edit').status_code == 400
        assert client.get('/cameras/missing/edit').status_code == 400
