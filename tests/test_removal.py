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
    csrf = re.search(r'name="csrf"[^>]*value="([^"]+)"', client.get('/').text)[1]
    if key == OWNER:
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'configure'})
    return csrf


def test_old_question_remove_restore_links_only_open_delete_confirmation(app):
    store = app.state.store
    app.state.pipeline.run(SID)
    before = store.observations()
    with TestClient(app) as client:
        csrf = login(client)
        base = f'/ui/questions/{SID}/red_square'
        for route in ('remove', 'restore'):
            response = client.post(base+'/'+route, data={'csrf':csrf})
            assert response.url.path == base+'/delete'
            assert 'Delete question and data' in response.text
            assert not store.is_removed(SID, 'red_square')
            assert store.observations() == before
        assert base+'/remove' not in client.get('/?view=questions').text


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
            from test_question_data_deletion import fields
            url = f'/ui/questions/{SID}/{qid}/delete'
            assert client.post(url, data=fields(client.get(url))).status_code == 200
        assert app.state.store.questions(SID) == []
        with pytest.raises(ProviderError, match='Enable at least one'):
            pipeline.run(SID)
        exported = configuration(pipeline.settings, app.state.store, app.state.reliable)
        path = tmp_path / 'no-questions.json'
        path.write_text(json.dumps(exported['config']))
        assert load_config(path).sources[0].questions == ()


def test_removal_permissions_and_csrf(app):
    url = f'/ui/sources/{SID}/remove'
    with TestClient(app) as client:
        assert client.post(url).status_code == 401
        login(client, VIEWER)
        assert client.get(url).status_code == 403
        assert client.post(url).status_code == 403
        client.cookies.clear()
        csrf = login(client)
        assert client.post(url).status_code == 403



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
    from test_question_data_deletion import fields
    url = f'/ui/questions/{SID}/red_square/delete'
    assert client.post(url, data=fields(client.get(url))).status_code == 200
    assert reliable.alerts() == []
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


def test_permanent_removed_question_delete_erases_target_history_restart_and_backup(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app.state.sampler, 'start', lambda: None)
    monkeypatch.setattr(app.state.reliable, 'start', lambda: None)
    store, pipeline = app.state.store, app.state.pipeline
    pipeline.run(SID)
    current = store.questions(SID)[0]['spec']
    store.edit_question(SID, replace(current, text='Updated red square'), store.policy(SID, 'red_square', '1'), expected_version='1')
    pipeline.run(SID)
    app.state.reliable.save_rule({'id': 'deleted-question-rule', 'source_id': SID, 'question_id': 'red_square', 'kind': 'count', 'threshold': 1, 'enabled': True})
    base = f'/ui/questions/{SID}/red_square'
    with TestClient(app) as client:
        csrf = login(client)
        assert client.post(base+'/remove', data={'csrf': csrf}).status_code == 200
        before = store.observations(limit=100)
        events = [e for e in store.events() if e['question_id'] != 'red_square']
        page = client.get('/?view=questions')
        assert base+'/delete' in page.text
        preview = client.get(base+'/delete')
        assert 'It cannot be restored from the app' in preview.text
        assert any(r['spec'].question_id == 'red_square' for r in store.questions(SID, include_removed=True))
        assert client.post(base+'/delete', data={'csrf': csrf, 'expected_version': 'stale'}).status_code == 400
        fingerprint = re.search(r'name="expected_data"[^>]*value="([^"]+)"', preview.text)[1]
        assert client.post(base+'/delete', data={'csrf': csrf, 'expected_version': '2', 'expected_data': fingerprint}).status_code == 200
        assert base+'/delete' not in client.get('/?view=questions').text
        assert base+'/restore' not in client.get('/?view=questions').text
        assert all(r['spec'].question_id != 'red_square' for r in store.questions(SID, include_removed=True))
        after = store.observations(limit=100)
        assert all(o['question_id'] != 'red_square' for o in after)
        assert {o['id']: o['answer']['value'] for o in after} == {o['id']: o['answer']['value'] for o in before if o['question_id'] != 'red_square'}
        assert store.events() == events
        assert app.state.reliable.rules()[0]['enabled'] is False
        app.state.reliable.evaluate()
        assert client.post(base+'/restore', data={'csrf': csrf}).status_code == 400
        assert client.get(base+'/delete').status_code == 400
        # Explicit old IDs remain reserved; replacement questions can receive a new ID.
        form = {'csrf': csrf, 'question_id': 'red_square', 'text': 'Red square', 'kind': 'binary', 'max_gap_seconds': '60'}
        assert client.post(f'/ui/questions/{SID}/new', data=form).status_code == 400
        form['question_id'] = ''
        assert client.post(f'/ui/questions/{SID}/new', data=form).status_code == 200
        assert 'red_square_2' in {r['spec'].question_id for r in store.questions(SID)}
    with store.connection() as db:
        assert db.execute('SELECT enabled,current_version FROM query_controls WHERE source_id=? AND question_id=?', (SID, 'red_square')).fetchone()[:] == (0, '2')
        assert db.execute("SELECT 1 FROM release_settings WHERE id=?", ('deleted_question:'+SID+':red_square',)).fetchone()
        assert db.execute('SELECT 1 FROM question_versions WHERE source_id=? AND question_id=?', (SID, 'red_square')).fetchone()
        assert db.execute("SELECT 1 FROM audit WHERE action='question_delete'").fetchone()
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    fresh = create_app(pipeline.settings, token=OWNER)
    assert all(r['spec'].question_id != 'red_square' for r in fresh.state.store.questions(SID, include_removed=True))
    assert fresh.state.store.observations(limit=100) == after
    assert fresh.state.store.events() == events
    config = configuration(pipeline.settings, store, app.state.reliable)
    saved = backup(store, config, tmp_path/'deleted-question-backup')
    restored = restore(saved, tmp_path/'deleted-question-restored')
    recovered = create_app(load_config(restored), token=OWNER)
    assert all(r['spec'].question_id != 'red_square' for r in recovered.state.store.questions(SID, include_removed=True))
    assert recovered.state.store.observations(limit=100) == after
    assert recovered.state.store.events() == events


def test_permanent_question_delete_permissions_csrf_and_active_guard(app, monkeypatch):
    monkeypatch.setattr(app.state.sampler, 'start', lambda: None)
    monkeypatch.setattr(app.state.reliable, 'start', lambda: None)
    base = f'/ui/questions/{SID}/red_square'
    with TestClient(app) as client:
        assert client.get(base+'/delete').status_code == 401
        assert client.post(base+'/delete', headers={'Authorization': 'Bearer '+VIEWER}).status_code == 403
        csrf = login(client)
        assert client.get(base+'/delete').status_code == 200  # Active questions delete directly.
        client.post(base+'/remove', data={'csrf': csrf})
        assert client.post(base+'/delete', data={'expected_version': '1'}).status_code == 403
        form = {'csrf': csrf, 'expected_version': '1'}
        assert any(r['spec'].question_id == 'red_square' for r in app.state.store.questions(SID, include_removed=True))
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        assert client.post(base+'/delete', data=form).status_code == 403
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'configure'})
        # Missing data confirmation must never delete a question.
        assert 'Question setup or alert rules changed' in client.post(base+'/delete', data=form).text
        assert any(r['spec'].question_id == 'red_square' for r in app.state.store.questions(SID))
