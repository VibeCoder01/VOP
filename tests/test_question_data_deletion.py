"""Optional question-history erasure uses disposable synthetic inputs only."""
from dataclasses import replace
from datetime import timedelta
import json
import re

import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER
from vop.contracts import utcnow
from vop.history_deletion import selection, delete_selected
from vop.inputs.sources import capture_inline
from vop.measurements import QueryPolicy
from vop.service import create_app
from vop.storage import dumps
from vop.reliable import backup, configuration, restore
from vop.config import load_config

SID, QID = 'synthetic-scene', 'red_square'
URL = f'/ui/questions/{SID}/{QID}/delete'
SENTINEL = 'synthetic-question-private-raw-detail'


@pytest.fixture(autouse=True)
def no_background_workers(app, monkeypatch):
    monkeypatch.setattr(app.state.sampler, 'start', lambda: None)
    monkeypatch.setattr(app.state.reliable, 'start', lambda: None)


def fields(page):
    return {name: re.search(r'name="'+name+r'"[^>]*value="([^"]+)"', page.text)[1]
            for name in ('csrf', 'expected_version', 'expected_data')}


def capture(app, seconds, sid=SID):
    frame = replace(capture_inline(app.state.pipeline.sources[sid]), captured_at_utc=utcnow()-timedelta(seconds=seconds))
    result = app.state.pipeline.run(sid, frame)
    return result, frame


def test_optional_delete_purges_question_versions_and_images_but_preserves_other_answers(app, tmp_path):
    store, pipeline = app.state.store, app.state.pipeline
    store.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=0)
    old, old_frame = capture(app, 60)
    question = store.questions(SID)[0]['spec']
    store.edit_question(SID, replace(question, text='Updated synthetic question'), QueryPolicy(positive_confirmations=1, negative_confirmations=1, max_gap_seconds=120), expected_version='1')
    shared, shared_frame = capture(app, 50)
    with store.connection() as db:
        db.execute('UPDATE query_controls SET enabled=0 WHERE source_id=? AND question_id!=?', (SID, QID))
    exclusive, exclusive_frame = capture(app, 40)
    app.state.reliable.save_rule({'id': 'target-rule', 'source_id': SID, 'question_id': QID, 'kind': 'duration', 'threshold': 0, 'enabled': True, 'webhook': True})
    app.state.reliable.evaluate()
    assert app.state.reliable.alerts(question_id=QID)
    # An earlier capture was deleted, leaving timestamp-only gaps for several questions.
    old_observation = next(o for o in store.observations(limit=100) if o['run_id'] == old['run_id'])
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        chosen = selection(db, observation_id=old_observation['id'])
        delete_selected(db, chosen)
        for key in chosen['keys']: store._rebuild(db, *key)
        db.execute('UPDATE query_controls SET enabled=CASE WHEN question_id=? THEN 0 ELSE 1 END WHERE source_id=?', (QID, SID))
    other_only, other_frame = capture(app, 30)
    with store.connection() as db:
        db.execute('UPDATE query_controls SET enabled=1 WHERE source_id=? AND question_id=?', (SID, QID))
        body = json.loads(db.execute('SELECT result_json FROM runs WHERE id=?', (shared['run_id'],)).fetchone()[0])
        body.update(provider_raw={'target': SENTINEL}, usage={'raw': SENTINEL})
        for answer in body['answers']: answer['raw_provider_fields'] = {'shared': SENTINEL}
        db.execute('UPDATE runs SET result_json=? WHERE id=?', (dumps(body), shared['run_id']))
        for row in db.execute('SELECT id,answer_json FROM observations WHERE run_id=?', (shared['run_id'],)).fetchall():
            answer = json.loads(row['answer_json'])
            answer['raw_provider_fields'] = {'shared': SENTINEL}
            db.execute('UPDATE observations SET answer_json=? WHERE id=?', (dumps(answer), row['id']))
    other_source = replace(pipeline.sources[SID], source_id='other-input')
    store.configure(replace(pipeline.settings, sources=(other_source,)))
    pipeline.sources['other-input'] = other_source
    store.update_source('other-input', enabled=True, retain_evidence=True, sample_interval_seconds=0)
    untouched, untouched_frame = capture(app, 20, 'other-input')
    untouched_answers = store.observations('other-input')
    with TestClient(app) as client:
        csrf = login(client)
        client.post(f'/ui/questions/{SID}/{QID}/remove', data={'csrf': csrf})
        before = {o['id']: o['answer'] for o in store.observations(SID, limit=100) if o['question_id'] != QID}
        other_events = [e for e in store.events() if e['source_id'] != SID or e['question_id'] != QID]
        pipeline.latest_preview = (SID, shared_frame.frame_id, b'cached-synthetic-preview')
        preview = client.get(URL)
        assert 'Also delete all recorded data' in preview.text
        assert '1 saved image is shared' in preview.text
        assert 'Those images will disappear from their results too' in preview.text
        assert 'name="delete_data"' in preview.text and 'name="delete_data" checked' not in preview.text
        form = {**fields(preview), 'delete_data': 'on'}
        result = client.post(URL, data=form)
        assert result.status_code == 200 and 'Recorded data deleted' in result.text
        assert pipeline.latest_preview is None
        for frame in (shared_frame, exclusive_frame):
            assert client.get(f'/ui/evidence/{SID}/{frame.frame_id}').status_code == 404
            assert client.get(f'/ui/preview/{SID}/{frame.frame_id}').status_code == 404
        assert client.get(f'/ui/evidence/{SID}/{other_frame.frame_id}').status_code == 200
        with store.connection() as db:
            assert not db.execute('SELECT 1 FROM observations WHERE source_id=? AND question_id=?', (SID, QID)).fetchone()
            assert not db.execute('SELECT 1 FROM events WHERE source_id=? AND question_id=?', (SID, QID)).fetchone()
            assert not db.execute('SELECT 1 FROM alerts WHERE source_id=? AND question_id=?', (SID, QID)).fetchone()
            assert not db.execute('SELECT 1 FROM deliveries').fetchone()
            assert not db.execute('SELECT 1 FROM runs WHERE id=?', (exclusive['run_id'],)).fetchone()
            assert not db.execute('SELECT 1 FROM frames WHERE source_id=? AND frame_id=?', (SID, exclusive_frame.frame_id)).fetchone()
            assert db.execute("SELECT 1 FROM audit WHERE action='question_data_delete'").fetchone()
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            assert all(SENTINEL not in row[0] for row in db.execute('SELECT result_json FROM runs'))
            assert all(SENTINEL not in row[0] for row in db.execute('SELECT answer_json FROM observations'))
            assert db.execute("SELECT count(*) FROM observations WHERE source_id=? AND status='retention_gap'", (SID,)).fetchone()[0] == 2
        after = {o['id']: o['answer'] for o in store.observations(SID, limit=100)}
        assert set(after) == set(before)
        for oid, answer in after.items():
            kept = {k: v for k, v in answer.items() if k not in ('raw_provider_fields', 'usage')}
            original = {k: v for k, v in before[oid].items() if k not in ('raw_provider_fields', 'usage')}
            assert kept == original
        assert [e for e in store.events() if e['source_id'] != SID or e['question_id'] != QID] == other_events
        assert store.observations('other-input') == untouched_answers
        assert store.evidence('other-input', untouched_frame.frame_id)
        assert store.source_control(SID)['retain_evidence'] is True  # Future image setting is unchanged.
    fresh = create_app(pipeline.settings, token=OWNER)
    assert not any(o['question_id'] == QID for o in fresh.state.store.observations(SID, limit=100))
    assert not any(e['source_id'] == SID and e['question_id'] == QID for e in fresh.state.store.events())
    saved = backup(store, configuration(pipeline.settings, store, app.state.reliable), tmp_path/'backup')
    restored = create_app(load_config(restore(saved, tmp_path/'restored')), token=OWNER)
    assert not any(o['question_id'] == QID for o in restored.state.store.observations(SID, limit=100))
    assert restored.state.store.evidence(SID, shared_frame.frame_id) is None


def test_purge_needs_current_counts_and_is_atomic(app, monkeypatch):
    store, pipeline = app.state.store, app.state.pipeline
    store.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=0)
    capture(app, 20)
    with TestClient(app) as client:
        csrf = login(client)
        client.post(f'/ui/questions/{SID}/{QID}/remove', data={'csrf': csrf})
        preview = client.get(URL)
        form = {**fields(preview), 'delete_data': 'on'}
        assert client.post(URL, data={**form, 'csrf': 'wrong'}).status_code == 403
        assert client.post(URL, data={**form, 'delete_data': 'invalid'}).status_code == 400
        assert client.post(URL, data=form, headers={'Authorization': 'Bearer '+VIEWER}).status_code == 403
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        assert client.post(URL, data=form).status_code == 403
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'configure'})
        for lock in (pipeline.busy, app.state.reliable.lock):
            lock.acquire()
            try:
                assert client.post(URL, data=form).status_code == 429
            finally:
                lock.release()
        missing = client.post(URL, data={**form, 'expected_data': ''})
        assert 'Recorded data changed. Review the updated counts' in missing.text
        assert any(q['spec'].question_id == QID for q in store.questions(SID, include_removed=True))
        # An image deletion after preview invalidates the recorded-data confirmation.
        with store.connection() as db: db.execute('UPDATE frames SET evidence_png=NULL WHERE source_id=?', (SID,))
        changed = client.post(URL, data=form)
        assert 'Recorded data changed. Review the updated counts' in changed.text
        assert any(q['spec'].question_id == QID for q in store.questions(SID, include_removed=True))
        before = store.observations(SID, limit=100)
        def fail(db, chosen):
            db.execute('DELETE FROM observations WHERE source_id=? AND question_id=?', (SID, QID))
            raise RuntimeError('synthetic deletion failure')
        monkeypatch.setattr('vop.removal.delete_question_data', fail)
        with pytest.raises(RuntimeError, match='synthetic deletion failure'):
            client.post(URL, data={**fields(changed), 'delete_data': 'on'})
        assert store.observations(SID, limit=100) == before
        assert any(q['spec'].question_id == QID for q in store.questions(SID, include_removed=True))
        assert not pipeline.busy.locked() and not app.state.reliable.lock.locked()


def test_leaving_recorded_data_option_off_keeps_answers_and_images(app):
    from bs4 import BeautifulSoup
    store = app.state.store
    store.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=0)
    _, frame = capture(app, 10)
    image = store.evidence(SID, frame.frame_id)
    with TestClient(app) as client:
        csrf = login(client)
        client.post(f'/ui/questions/{SID}/{QID}/remove', data={'csrf': csrf})
        before = store.observations(SID, limit=100)
        preview = client.get(URL)
        checkbox = BeautifulSoup(preview.text, 'html.parser').find('input', attrs={'name': 'delete_data'})
        assert checkbox is not None and not checkbox.has_attr('checked')
        assert store.observations(SID, limit=100) == before
        assert client.post(URL, data=fields(preview)).status_code == 200
        assert store.observations(SID, limit=100) == before
        assert store.evidence(SID, frame.frame_id) == image
        assert client.get(f'/ui/evidence/{SID}/{frame.frame_id}').status_code == 200
