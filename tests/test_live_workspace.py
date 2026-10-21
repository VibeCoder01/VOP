from dataclasses import replace
import json
import sqlite3

import pytest
from starlette.testclient import TestClient

from test_phase2_browser_storage import settings, OWNER, login
from vop.inputs.sources import capture_inline
from vop.service import create_app
from vop.storage import dumps
from vop.live_workspace import prepare


def test_cleanup_removes_only_test_records_and_cannot_reseed_on_restart(settings):
    sample = settings.sources[0]
    camera = replace(sample, source_id='camera-fixture', name='Fixture camera', kind='usb', settings={'device': 0})
    settings = replace(settings, sources=(sample, camera))
    app = create_app(settings, token=OWNER)
    pipeline, store = app.state.pipeline, app.state.store
    pipeline.run(sample.source_id)
    pipeline.run(camera.source_id, replace(capture_inline(sample), source_id=camera.source_id))
    # Offline fixture explicitly marks this next result non-synthetic to test preservation.
    pipeline.engine.synthetic = False
    result = pipeline.run(camera.source_id, replace(capture_inline(sample), source_id=camera.source_id))
    real_ids = {r['id'] for r in store.observations(camera.source_id) if not r['provenance']['synthetic']}
    app.state.reliable.save_rule({'id': 'fixture-rule', 'source_id': sample.source_id, 'question_id': sample.questions[0].question_id, 'kind': 'duration'})
    app.state.reliable.save_rule({'id': 'keep-rule', 'source_id': camera.source_id, 'question_id': sample.questions[0].question_id, 'kind': 'duration'})
    store.audit('fixture_setup', dumps({'source_id': sample.source_id}))
    with store.connection() as db:
        db.execute('INSERT INTO release_settings VALUES(?,?)', ('saved_engine:fixture', dumps({'name': 'Fixture demo', 'profile': {'kind': 'mock'}})))
        for aid, synthetic in (('remove-alert', True), ('keep-alert', False)):
            db.execute('INSERT INTO alerts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (aid, 'keep-rule', 1, '2026-10-21T00:00:00+00:00', 'duration', 'info', camera.source_id,
                        sample.questions[0].question_id, '1', None, 'open', '', dumps({'synthetic': synthetic})))
            db.execute('INSERT INTO deliveries VALUES(?,?,?,?,?)', (aid, 'dashboard', 'delivered', 1, '2026-10-21T00:00:00+00:00'))
    live = create_app(settings, token=OWNER, live_workspace=True)
    assert list(live.state.pipeline.sources) == [camera.source_id]
    assert live.state.pipeline.engine.synthetic is False
    assert {r['id'] for r in live.state.store.observations(camera.source_id)} == real_ids
    assert [r['id'] for r in live.state.reliable.rules()] == ['keep-rule']
    assert [r['id'] for r in live.state.reliable.alerts()] == ['keep-alert']
    with store.connection() as db:
        assert not db.execute('SELECT 1 FROM sources WHERE id=?', (sample.source_id,)).fetchone()
        assert not db.execute('SELECT 1 FROM mock_values').fetchone()
        assert not db.execute("SELECT 1 FROM deliveries WHERE alert_id='remove-alert'").fetchone()
        assert db.execute("SELECT 1 FROM deliveries WHERE alert_id='keep-alert'").fetchone()
        assert not db.execute("SELECT 1 FROM audit WHERE action='fixture_setup'").fetchone()
        assert db.execute("SELECT count(*) FROM observations WHERE source_id=? AND status='retention_gap'", (camera.source_id,)).fetchone()[0] == len(sample.questions)
        assert len(db.execute("SELECT name FROM sqlite_master WHERE name IN ('immutable_question_delete','immutable_rule_delete')").fetchall()) == 2
        with pytest.raises(sqlite3.IntegrityError):
            db.execute('DELETE FROM question_versions WHERE source_id=?', (camera.source_id,))
    again = create_app(settings, token=OWNER, live_workspace=True)
    assert again.state.pipeline.workspace_cleanup == dict.fromkeys(('inputs', 'captures', 'alerts', 'rules', 'engines', 'audit'), 0)
    assert again.state.store.health()['observation_count'] == len(sample.questions)
    with TestClient(again) as client:
        csrf = login(client)
        for path in ('/engines', '/engines/new', '/release', '/?view=questions'):
            text = client.get(path).text
            assert 'Synthetic shapes' not in text and 'Mock answer' not in text
            assert '>Demo</a>' not in text and 'Synthetic worker (test only)' not in text
        assert client.get('/engines/new?kind=mock').status_code == 400
        assert client.post('/integration/engine', data={'csrf': csrf, 'kind': 'mock'}).status_code == 400


def test_cleanup_rolls_back_data_and_triggers_if_a_record_is_invalid(settings):
    app = create_app(settings, token=OWNER)
    app.state.pipeline.run(settings.sources[0].source_id)
    store = app.state.store
    before = store.health()
    with store.connection() as db:
        db.execute('INSERT INTO release_settings VALUES(?,?)', ('saved_engine:broken', dumps({'invalid': True})))
    with pytest.raises(KeyError):
        prepare(store, settings)
    assert store.health() == before
    with store.connection() as db:
        assert db.execute('SELECT 1 FROM sources').fetchone()
        assert len(db.execute("SELECT name FROM sqlite_master WHERE name IN ('immutable_question_delete','immutable_rule_delete')").fetchall()) == 2
