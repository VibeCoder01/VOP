"""Destructive paths use disposable synthetic databases only."""
from dataclasses import replace
from datetime import timedelta
import json
import re

import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER
from vop.contracts import utcnow
from vop.inputs.sources import capture_inline
from vop.service import create_app

SID = 'synthetic-scene'


def captures(app, count=3, sid=SID):
    app.state.store.update_source(sid, enabled=True, retain_evidence=True, sample_interval_seconds=0)
    now = utcnow()
    runs = []
    for number in range(count):
        frame = replace(capture_inline(app.state.pipeline.sources[sid]), captured_at_utc=now - timedelta(seconds=(count - number) * 10))
        result = app.state.pipeline.run(sid, frame)
        runs.append((result['run_id'], frame))
    return runs


def expected(page):
    return re.search(r'name="expected"[^>]*value="([^"]+)"', page.text)[1]


def observation_for(app, run_id):
    return next(o for o in app.state.store.observations(limit=100) if o['run_id'] == run_id)


def test_capture_delete_removes_shared_data_and_replays_with_unknown_gap(app):
    runs = captures(app)
    oid = observation_for(app, runs[1][0])['id']
    before = app.state.store.summary(SID, 'red_square', '1')
    assert before['covered_seconds'] > 0
    with TestClient(app) as client:
        csrf = login(client)
        url = '/ui/observations/' + oid + '/delete'
        preview = client.get(url)
        assert '1 captures · 3 answers · 1 retained images' in preview.text
        assert len(app.state.store.observations()) == 9  # GET is read-only.
        result = client.post(url, data={'csrf': csrf, 'expected': expected(preview)})
        assert result.status_code == 200 and result.url.path == '/observations'
        assert app.state.store.observation(oid) is None
        assert app.state.store.evidence(SID, runs[1][1].frame_id) is None
        assert client.get('/ui/observations/' + oid).status_code == 404
        assert client.get('/ui/evidence/' + SID + '/' + runs[1][1].frame_id).status_code == 404
        assert len(app.state.store.observations()) == 6
        assert app.state.store.health()['observation_count'] == 6
    summary = app.state.store.summary(SID, 'red_square', '1')
    assert summary['covered_seconds'] == 0 and summary['unknown_seconds'] == 20
    assert summary['sample_count'] == summary['valid_sample_count'] == 2
    with app.state.store.connection() as db:
        assert not db.execute('SELECT 1 FROM runs WHERE id=?', (runs[1][0],)).fetchone()
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        marker = db.execute("SELECT id FROM observations WHERE status='retention_gap' LIMIT 1").fetchone()[0]
    assert app.state.store.observation(marker) is None
    exported = app.state.reliable.export('metrics')['rows']
    assert all(p['engine_id'] != 'retention-gap' for r in exported for p in r['provenance'])
    restarted = create_app(app.state.pipeline.settings, token=OWNER)
    assert len(restarted.state.store.observations()) == 6
    assert restarted.state.store.summary(SID, 'red_square', '1')['covered_seconds'] == 0


def test_input_history_delete_keeps_configuration_other_input_and_clears_gaps(app):
    runs = captures(app)
    other = replace(app.state.pipeline.sources[SID], source_id='other')
    app.state.store.configure(replace(app.state.pipeline.settings, sources=(other,)))
    app.state.pipeline.sources['other'] = other
    captures(app, 1, 'other')
    with TestClient(app) as client:
        csrf = login(client)
        single = '/ui/observations/' + observation_for(app, runs[0][0])['id'] + '/delete'
        preview = client.get(single)
        client.post(single, data={'csrf': csrf, 'expected': expected(preview)})
        url = '/ui/sources/' + SID + '/history/delete'
        preview = client.get(url)
        assert '2 captures · 6 answers' in preview.text
        assert client.post(url, data={'csrf': csrf, 'expected': expected(preview)}).status_code == 200
    assert app.state.store.observations(SID) == []
    assert len(app.state.store.observations('other')) == 3
    assert SID in app.state.pipeline.sources and len(app.state.store.questions(SID)) == 3
    with app.state.store.connection() as db:
        assert not db.execute('SELECT 1 FROM runs WHERE source_id=?', (SID,)).fetchone()
        assert not db.execute('SELECT 1 FROM frames WHERE source_id=?', (SID,)).fetchone()
        assert not db.execute("SELECT 1 FROM observations WHERE source_id=? AND status='retention_gap'", (SID,)).fetchone()
        assert len(db.execute('SELECT * FROM question_versions WHERE source_id=?', (SID,)).fetchall()) == 3


def test_delete_clears_related_alerts_deliveries_and_pauses_rules(app):
    runs = captures(app)
    reliable = app.state.reliable
    reliable.save_rule({'id': 'red-rule', 'source_id': SID, 'question_id': 'red_square', 'kind': 'duration', 'threshold': 0, 'webhook': True})
    reliable.evaluate()
    assert reliable.alerts()
    client = TestClient(app)  # Keep the delivery worker stopped.
    csrf = login(client)
    url = '/ui/observations/' + observation_for(app, runs[1][0])['id'] + '/delete'
    preview = client.get(url)
    assert '1 related alerts' in preview.text and '1 affected alert rules' in preview.text
    assert client.post(url, data={'csrf': csrf, 'expected': expected(preview)}).status_code == 200
    assert reliable.alerts() == [] and reliable.rules()[0]['enabled'] is False
    with app.state.store.connection() as db:
        assert not db.execute('SELECT 1 FROM deliveries').fetchone()
        assert db.execute('SELECT count(*) FROM rule_versions').fetchone()[0] == 2
    client.close()


def test_deletion_permissions_csrf_busy_and_changed_preview(app):
    runs = captures(app, 1)
    url = '/ui/sources/' + SID + '/history/delete'
    with TestClient(app) as client:
        assert client.get(url).status_code == 401
        assert client.get(url, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        csrf = login(client)
        preview = client.get(url)
        form = {'csrf': csrf, 'expected': expected(preview)}
        assert client.post(url, data={'expected': form['expected']}).status_code == 403
        app.state.pipeline.busy.acquire()
        try: assert client.post(url, data=form).status_code == 429
        finally: app.state.pipeline.busy.release()
        app.state.reliable.lock.acquire()
        try: assert client.post(url, data=form).status_code == 429
        finally: app.state.reliable.lock.release()
        captures(app, 1)
        changed = client.post(url, data=form)
        assert 'History changed. Review these updated counts' in changed.text
        assert len(app.state.store.observations()) == 6
        assert client.post(url, data={'csrf': csrf, 'expected': expected(changed)}).status_code == 200


def test_bulk_delete_requires_paused_monitoring_and_transaction_rolls_back(app, monkeypatch):
    captures(app, 1)
    client = TestClient(app)
    csrf = login(client)
    url = '/ui/sources/' + SID + '/history/delete'
    app.state.store.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=30)
    preview = client.get(url)
    assert 'Pause monitoring' in preview.text and 'disabled' in preview.text
    form = {'csrf': csrf, 'expected': expected(preview)}
    assert client.post(url, data=form).status_code == 400
    app.state.store.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=0)
    def fail(*args): raise RuntimeError('Fixture replay failure')
    monkeypatch.setattr(app.state.store, '_rebuild', fail)
    with pytest.raises(RuntimeError, match='Fixture replay failure'):
        client.post(url, data=form)
    assert len(app.state.store.observations()) == 3
    assert not app.state.pipeline.busy.locked() and not app.state.reliable.lock.locked()
    client.close()


def test_engine_delete_selected_guard_and_key_preservation(app):
    with TestClient(app) as client:
        csrf = login(client)
        current = app.state.pipeline.engine
        guarded = client.get('/engines/current/delete')
        assert 'Select another engine' in guarded.text
        assert client.post('/engines/current/delete', data={'csrf': csrf, 'expected': expected(guarded)}).status_code == 200
        body = {'csrf': csrf, 'name': 'Disposable', 'kind': 'worker', 'engine_id': 'test-worker', 'version': 'v1',
                'worker_id': 'fixture', 'url': 'http://127.0.0.1:8878', 'transport': 'local', 'worker_token': 't' * 40}
        client.post('/engines/new/save', data=body)
        with app.state.store.connection() as db:
            record = json.loads(db.execute("SELECT value_json FROM release_settings WHERE id='saved_engine:disposable'").fetchone()[0])
        url = '/engines/disposable/delete'
        assert client.get(url, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        preview = client.get(url)
        assert client.post(url, data={'csrf': csrf, 'expected': expected(preview)}).url.path == '/engines'
        assert client.get('/engines/disposable').status_code == 400
        assert app.state.secrets.get(record['profile']['secret_ref']) == 't' * 40
        assert app.state.pipeline.engine is current


def test_observations_page_lists_removed_source_history_and_remove_links(app):
    captures(app, 1)
    with TestClient(app) as client:
        csrf = login(client)
        page = client.get('/observations?source=' + SID)
        assert page.status_code == 200 and 'Delete capture' in page.text and 'Delete input history' in page.text
        assert client.post('/ui/sources/' + SID + '/remove', data={'csrf': csrf}).status_code == 200
        assert client.get('/observations?source=' + SID).status_code == 200
        assert 'Delete profile' in client.get('/engines/current/delete').text


def test_camera_remove_is_visible_and_restore_returns_to_cameras(app):
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/cameras/save', data={'csrf': csrf, 'model': 'C200', 'endpoint': 'rtsp://192.168.1.200:554/stream1',
                                          'username': 'fixture-user', 'password': 'fixture-password'})
        path = '/ui/sources/tapo-c200/remove'
        assert path in client.get('/cameras').text
        assert 'Remove camera' in client.get('/cameras/tapo-c200').text
        preview = client.get(path)
        assert 'Protected camera details are retained' in preview.text
        removed = client.post(path, data={'csrf': csrf})
        assert removed.url.path == '/cameras' and 'Removed cameras' in removed.text
        restored = client.post('/ui/sources/tapo-c200/restore', data={'csrf': csrf})
        assert restored.url.path == '/cameras' and 'tapo-c200' in restored.text
        assert app.state.store.source_control('tapo-c200')['enabled'] is False


def test_delete_only_capture_keeps_unknown_without_fake_answers_or_ids(app):
    runs = captures(app, 1)
    with TestClient(app) as client:
        csrf = login(client)
        url = '/ui/observations/' + observation_for(app, runs[0][0])['id'] + '/delete'
        preview = client.get(url)
        client.post(url, data={'csrf': csrf, 'expected': expected(preview)})
        assert app.state.store.health()['observation_count'] == 0
        summary = app.state.store.summary(SID, 'red_square', '1')
        assert summary['state'] == 'UNKNOWN' and summary['sample_count'] == 0
        assert summary['last_observation_id'] is None and summary['latest_value'] is None
        full = client.get('/ui/sources/' + SID + '/history/delete')
        assert '3 timestamp-only gap markers' in full.text
