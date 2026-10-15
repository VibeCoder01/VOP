"""Configuration removal is offline, recoverable and independent of history."""
from dataclasses import replace
from datetime import timedelta
import json
from pathlib import Path
import re

import pytest
from starlette.testclient import TestClient

from vop.config import load_config
from vop.contracts import ProviderError, utcnow
from vop.inputs.sources import capture_inline
from vop.service import create_app
from vop.reliable import configuration, backup, restore

OWNER, VIEWER = 'o' * 40, 'v' * 40
SID = 'synthetic-scene'


@pytest.fixture
def app(tmp_path):
    body = json.loads((Path(__file__).resolve().parents[1] / 'sample-config/phase1.json').read_text())
    path = tmp_path / 'config.json'
    body['database'] = 'test.sqlite3'
    path.write_text(json.dumps(body))
    return create_app(load_config(path), token=OWNER, viewer_token=VIEWER)


def login(client, key=OWNER):
    csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', client.get('/login').text)[1]
    client.post('/login', data={'csrf': csrf, 'access_key': key})
    return re.search(r'name="csrf"[^>]*value="([^"]+)"', client.get('/').text)[1]


def test_question_removal_history_restart_restore_and_alert_rules(app):
    store, pipeline, reliable = app.state.store, app.state.pipeline, app.state.reliable
    pipeline.run(SID)
    original = store.observations()
    reliable.save_rule({'id': 'red-rule', 'source_id': SID, 'question_id': 'red_square', 'kind': 'duration', 'threshold': 1,
                        'window_seconds': 60, 'severity': 'warning', 'enabled': True, 'webhook': False})
    with TestClient(app) as client:
        csrf = login(client)
        url = f'/ui/questions/{SID}/red_square/remove'
        assert url in client.get('/?view=questions').text
        assert 'immutable versions remain' in client.get(url).text
        assert not store.is_removed(SID, 'red_square')  # GET is confirmation only.
        assert client.post(url, data={'csrf': csrf}).status_code == 200
        assert store.is_removed(SID, 'red_square')
        assert [q['spec'].question_id for q in store.questions(SID)] == ['background', 'brightness']
        assert all(store.observation(o['id'])['answer'] == o['answer'] for o in original)
        assert reliable.rules()[0]['enabled'] is False
        assert reliable.rules()[0]['revision'] == 2
        reliable.evaluate()  # Removed questions do not crash the rule worker.
        with pytest.raises(ValueError, match='Restore'):
            store.edit_question(SID, pipeline.sources[SID].questions[0], store.policy(SID, 'red_square', '1'))
    restarted = create_app(pipeline.settings, token=OWNER)
    assert restarted.state.store.is_removed(SID, 'red_square')
    assert 'red_square' not in [q['spec'].question_id for q in restarted.state.store.questions(SID)]
    with TestClient(restarted) as client:
        csrf = login(client)
        assert 'Removed questions' in client.get('/?view=questions').text
        assert client.post(f'/ui/questions/{SID}/red_square/restore', data={'csrf': csrf}).status_code == 200
        record = next(q for q in store.questions(SID) if q['spec'].question_id == 'red_square')
        assert record['enabled'] is False and record['spec'].version == '1'
        assert reliable.rules()[0]['enabled'] is False


def test_remove_all_sources_backup_restart_and_safe_restore(app, tmp_path, monkeypatch):
    # Test persisted scheduling controls without racing an unrelated background capture.
    monkeypatch.setattr(app.state.sampler, 'start', lambda: None)
    store, pipeline = app.state.store, app.state.pipeline
    pipeline.run(SID)
    original_ids = {o['id'] for o in store.observations()}
    store.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=10)
    with TestClient(app) as client:
        csrf = login(client)
        assert client.post(f'/ui/sources/{SID}/remove', data={'csrf': csrf}).status_code == 200
        assert not pipeline.sources and SID in pipeline.removed_sources
        assert 'Removed sources' in client.get('/?view=sources').text
        assert client.get('/api/v1/sources').json()['sources'] == []
        with pytest.raises(ProviderError):
            pipeline.run(SID)
        assert original_ids <= {o['id'] for o in store.observations()}
    package = configuration(pipeline.settings, store, app.state.reliable)
    assert package['config']['sources'] == []
    path = tmp_path / 'empty.json'
    path.write_text(json.dumps(package['config']))
    assert load_config(path).sources == ()
    backup(store, package, tmp_path / 'backup')
    restored_config = restore(tmp_path / 'backup', tmp_path / 'restored')
    empty_settings = load_config(restored_config)
    restarted = create_app(empty_settings, token=OWNER)
    assert not restarted.state.pipeline.sources and SID in restarted.state.pipeline.removed_sources
    with TestClient(restarted) as client:
        csrf = login(client)
        assert client.post(f'/ui/sources/{SID}/restore', data={'csrf': csrf}).status_code == 200
    assert restarted.state.store.source_control(SID) == {'enabled': False, 'retain_evidence': False, 'sample_interval_seconds': 0}
    again = create_app(empty_settings, token=OWNER)
    assert SID in again.state.pipeline.sources
    assert again.state.store.source_control(SID)['enabled'] is False


def test_remove_all_questions_valid_empty_export_and_no_capture(app, tmp_path):
    pipeline = app.state.pipeline
    with TestClient(app) as client:
        csrf = login(client)
        for qid in ('red_square', 'background', 'brightness'):
            assert client.post(f'/ui/questions/{SID}/{qid}/remove', data={'csrf': csrf}).status_code == 200
        assert app.state.store.questions(SID) == []
        with pytest.raises(ProviderError, match='Enable at least one'):
            pipeline.run(SID)
        exported = configuration(pipeline.settings, app.state.store, app.state.reliable)
        path = tmp_path / 'no-questions.json'
        path.write_text(json.dumps(exported['config']))
        assert load_config(path).sources[0].questions == ()


def test_removal_permissions_csrf_and_busy_capture(app):
    url = f'/ui/sources/{SID}/remove'
    with TestClient(app) as client:
        assert client.post(url).status_code == 401
        login(client, VIEWER)
        assert client.get(url).status_code == 403
        assert client.post(url).status_code == 403
        client.cookies.clear()
        csrf = login(client)
        assert client.post(url).status_code == 403
        app.state.pipeline.busy.acquire()
        try:
            assert client.post(url, data={'csrf': csrf}).status_code == 429
            assert not app.state.store.is_removed(SID)
        finally:
            app.state.pipeline.busy.release()


def test_removal_cancels_pending_webhook_without_rewriting_alert(app):
    pipeline, reliable = app.state.pipeline, app.state.reliable
    now = utcnow()
    for seconds in (30, 20, 10):
        frame = replace(capture_inline(pipeline.sources[SID]), captured_at_utc=now - timedelta(seconds=seconds))
        pipeline.run(SID, frame)
    reliable.save_rule({'id': 'red-rule', 'source_id': SID, 'question_id': 'red_square', 'kind': 'duration', 'threshold': 0, 'webhook': True})
    reliable.evaluate(now)
    before = reliable.alerts()[0]
    assert any(d['status'] == 'pending' for d in before['deliveries'])
    # No lifespan worker: inspect the queued delivery deterministically.
    client = TestClient(app)
    csrf = login(client)
    assert client.post(f'/ui/questions/{SID}/red_square/remove', data={'csrf': csrf}).status_code == 200
    after = reliable.alerts()[0]
    assert before['payload'] == after['payload'] and before['id'] == after['id']
    assert any(d['status'] == 'cancelled' for d in after['deliveries'])
    def must_not_send(*args):
        pytest.fail('Removed question must not send queued webhooks')
    reliable.sender = must_not_send
    reliable.retry(now + timedelta(seconds=60))
    client.close()


def test_removed_camera_keeps_protected_setup_and_does_not_resurrect(app, monkeypatch):
    from vop.secrets import SecretStore
    values = {}
    monkeypatch.setattr(SecretStore, 'set', lambda self, name, value: values.update({name: value}))
    monkeypatch.setattr(SecretStore, 'get', lambda self, name: values[name])
    client = TestClient(app)
    csrf = login(client)
    body = {'csrf': csrf, 'source_id': 'tapo-test', 'model': 'C200', 'endpoint': 'rtsp://192.168.1.100:554/stream1', 'username': 'offline-user', 'password': 'offline-secret'}
    assert client.post('/integration/camera', data=body).status_code == 200
    assert client.post('/ui/sources/tapo-test/remove', data={'csrf': csrf}).status_code == 200
    protected = dict(values)
    assert client.post('/integration/camera', data=body).status_code == 400
    assert protected == values
    restarted = create_app(app.state.pipeline.settings, token=OWNER)
    assert 'tapo-test' not in restarted.state.pipeline.sources
    assert 'tapo-test' in restarted.state.pipeline.removed_sources
    with TestClient(restarted) as fresh:
        csrf = login(fresh)
        assert fresh.post('/ui/sources/tapo-test/restore', data={'csrf': csrf}).status_code == 200
        saved = fresh.get('/integration?camera=tapo-test').text
        assert '192.168.1.100' in saved and 'offline-secret' not in saved
    assert protected == values
    client.close()
