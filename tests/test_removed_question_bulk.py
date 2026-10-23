"""Bulk deletion is exercised only on disposable synthetic histories."""
from dataclasses import replace
import json

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER
from vop.history_deletion import delete_question_data
from vop.inputs.sources import capture_inline
from vop.service import create_app

SID = 'synthetic-scene'
BULK = '/ui/removed-questions/delete'
PAIRS = [[SID, 'red_square'], [SID, 'background']]


@pytest.fixture(autouse=True)
def no_workers(app, monkeypatch):
    monkeypatch.setattr(app.state.sampler, 'start', lambda: None)
    monkeypatch.setattr(app.state.reliable, 'start', lambda: None)


def setup_history(app):
    store, pipeline = app.state.store, app.state.pipeline
    first = replace(pipeline.sources[SID], name='Front door')
    second = replace(first, source_id='garden-fixture', name='Garden')
    store.configure(replace(pipeline.settings, sources=(first, second)))
    pipeline.sources.update({SID: first, second.source_id: second})
    for source in (first, second):
        store.update_source(source.source_id, enabled=True, retain_evidence=True, sample_interval_seconds=0)
        pipeline.run(source.source_id, capture_inline(source))
    old = store.questions(SID)[0]['spec']
    store.edit_question(SID, replace(old, text='Updated front door question'), store.policy(SID, old.question_id, old.version), expected_version=old.version)
    pipeline.run(SID, capture_inline(first))


def remove(client, csrf, pairs=PAIRS):
    for sid, qid in pairs:
        assert client.post(f'/ui/questions/{sid}/{qid}/remove', data={'csrf': csrf}).status_code == 200


def selection(csrf, pairs=PAIRS):
    return {'csrf': csrf, 'selection': [json.dumps(pair) for pair in pairs]}


def confirmation(page, route=BULK):
    soup = BeautifulSoup(page.text, 'html.parser')
    form = soup.find('form', action=route)
    result = {}
    for control in form.select('input[name]'):
        name, value = control['name'], control.get('value', '')
        if name == 'selection': result.setdefault(name, []).append(value)
        else: result[name] = value
    return result


def test_question_buttons_names_counts_and_source_filter(app):
    setup_history(app)
    with TestClient(app) as client:
        csrf = login(client)
        remove(client, csrf, PAIRS + [['garden-fixture', 'red_square']])
        page = client.get('/?view=questions&timezone=Invalid&from=not-a-date')
        assert page.status_code == 200
        soup = BeautifulSoup(page.text, 'html.parser')
        assert not soup.select('[name=timezone], select[name=source]')
        buttons = soup.select('nav.source-selectors a')
        assert [a.text for a in buttons] == ['All sources', 'Front door', 'Garden']
        assert buttons[0]['aria-current'] == 'page'
        removed = soup.select_one('.removed-questions')
        assert len(removed.select('input[type=checkbox][name=selection]')) == 3
        form_id = removed.find('form', action=BULK)['id']
        assert all(box['form'] == form_id for box in removed.select('input[name=selection]'))
        first_row = removed.select('tbody tr')[0]
        assert first_row.select('td')[1].text == 'Front door'
        with app.state.store.connection() as db:
            count = db.execute("SELECT count(*) FROM observations WHERE source_id=? AND question_id='red_square' AND status!='retention_gap'", (SID,)).fetchone()[0]
        assert int(first_row.select('td')[3].text) == count
        assert first_row.select('td')[4].get_text(' ', strip=True) == '2 2 shared'
        filtered = BeautifulSoup(client.get('/?view=questions&source=garden-fixture').text, 'html.parser')
        assert filtered.select_one('nav.source-selectors [aria-current=page]').text == 'Garden'
        rows = filtered.select('.removed-questions tbody tr')
        assert len(rows) == 1 and rows[0].select('td')[1].text == 'Garden'
        assert 'Updated front door question' not in filtered.text


def test_bulk_deletes_all_selected_versions_without_restoring_shared_answers(app):
    setup_history(app)
    store, pipeline = app.state.store, app.state.pipeline
    with TestClient(app) as client:
        csrf = login(client)
        remove(client, csrf)
        before = store.observations(SID, limit=100)
        other = store.observations('garden-fixture', limit=100)
        preview = client.post(BULK, data=selection(csrf, PAIRS + [PAIRS[0]]))
        assert preview.status_code == 200 and '2 selected questions' in preview.text
        assert store.observations(SID, limit=100) == before
        assert 'name="delete_data"' not in preview.text
        form = confirmation(preview)
        assert len(form['selection']) == 2
        response = client.post(BULK, data=form)
        assert response.status_code == 200 and 'recorded data deleted' in response.text
        assert {o['question_id'] for o in store.observations(SID, limit=100)} == {'brightness'}
        assert {o['id']: o['answer']['value'] for o in store.observations(SID, limit=100)} == {
            o['id']: o['answer']['value'] for o in before if o['question_id'] == 'brightness'}
        assert store.observations('garden-fixture', limit=100) == other
        assert SID not in pipeline.previews and 'garden-fixture' in pipeline.previews
        with store.connection() as db:
            for row in db.execute('SELECT result_json FROM runs WHERE source_id=?', (SID,)):
                body = json.loads(row[0])
                assert not any(a['question_id'] in ('red_square', 'background') for a in body['answers'])
                assert body['provider_raw'] is None
            assert not db.execute('SELECT 1 FROM frames WHERE source_id=? AND evidence_png IS NOT NULL', (SID,)).fetchone()
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
        fresh = create_app(pipeline.settings, token=OWNER)
        assert {r['spec'].question_id for r in fresh.state.store.questions(SID, include_removed=True)} == {'brightness'}
        assert {o['question_id'] for o in fresh.state.store.observations(SID, limit=100)} == {'brightness'}


def test_bulk_preview_staleness_restored_guard_and_atomic_rollback(app, monkeypatch):
    setup_history(app)
    store = app.state.store
    with TestClient(app) as client:
        csrf = login(client)
        remove(client, csrf)
        form = confirmation(client.post(BULK, data=selection(csrf)))
        with store.connection() as db:
            db.execute('UPDATE frames SET evidence_png=NULL WHERE source_id=?', (SID,))
        stale = client.post(BULK, data=form)
        assert 'Recorded data changed. Review the updated counts' in stale.text
        assert {r['spec'].question_id for r in store.questions(SID, include_removed=True)} == {'red_square', 'background', 'brightness'}
        form = confirmation(stale)
        before = store.observations(SID, limit=100)
        calls = []
        def fail_second(db, chosen):
            delete_question_data(db, chosen)
            calls.append(chosen['question_id'])
            if len(calls) == 2: raise RuntimeError('synthetic bulk failure')
        with monkeypatch.context() as patch:
            patch.setattr('vop.removal.delete_question_data', fail_second)
            with pytest.raises(RuntimeError, match='synthetic bulk failure'):
                client.post(BULK, data=form)
        assert len(calls) == 2 and store.observations(SID, limit=100) == before
        with store.connection() as db:
            assert not db.execute("SELECT 1 FROM release_settings WHERE id LIKE 'deleted_question:%'").fetchone()
        assert not app.state.pipeline.busy.locked() and not app.state.reliable.lock.locked()
        assert client.post(f'/ui/questions/{SID}/red_square/restore', data={'csrf': csrf}).status_code == 200
        assert client.post(BULK, data=form).status_code == 400
        assert store.observations(SID, limit=100) == before


def test_bulk_permissions_and_invalid_selections_do_not_delete(app):
    setup_history(app)
    with TestClient(app) as client:
        assert client.post(BULK, data=selection('bad')).status_code == 401
        csrf = login(client)
        remove(client, csrf)
        form = confirmation(client.post(BULK, data=selection(csrf)))
        before = app.state.store.observations(SID, limit=100)
        assert client.post(BULK, data={**form, 'csrf': 'bad'}).status_code == 403
        assert client.post(BULK, data=form, headers={'Authorization': 'Bearer '+VIEWER}).status_code == 403
        assert client.post(BULK, data=form, headers={'Origin':'http://elsewhere.example'}).status_code == 403
        for value in ([], ['invalid-json'], [json.dumps([SID])], [json.dumps([SID, 12])]):
            assert client.post(BULK, data={'csrf':csrf, 'selection':value}).status_code == 400
        assert client.post(BULK, data=selection(csrf, [PAIRS[0], [SID, 'brightness']])).status_code == 400
        client.post('/ui/mode', data={'csrf':csrf, 'mode':'view'})
        assert client.post(BULK, data=form).status_code == 403
        assert app.state.store.observations(SID, limit=100) == before


def test_bulk_can_delete_same_question_id_on_multiple_named_cameras(app):
    setup_history(app)
    pairs = [PAIRS[0], ['garden-fixture', 'red_square']]
    with TestClient(app) as client:
        csrf = login(client)
        remove(client, csrf, pairs)
        preview = client.post(BULK, data=selection(csrf, pairs))
        assert 'Front door' in preview.text and 'Garden' in preview.text
        assert client.post(BULK, data=confirmation(preview)).status_code == 200
        for sid in (SID, 'garden-fixture'):
            assert {o['question_id'] for o in app.state.store.observations(sid, limit=100)} == {'background', 'brightness'}
            assert sid not in app.state.pipeline.previews

@pytest.mark.parametrize('bulk', [False, True])
@pytest.mark.parametrize('changed_while_waiting', [False, True])
def test_confirmed_deletion_waits_and_rechecks_without_blocking_dashboard(app, monkeypatch, bulk, changed_while_waiting):
    from concurrent.futures import ThreadPoolExecutor
    from test_camera_save_queue import ObservedLock
    from vop.browser_auth import BrowserAuth

    setup_history(app)
    store = app.state.store
    with TestClient(app) as client:
        csrf = login(client)
        pairs = PAIRS if bulk else PAIRS[:1]
        remove(client, csrf, pairs)
        route = BULK if bulk else f'/ui/questions/{SID}/red_square/delete'
        preview = client.post(route, data=selection(csrf, pairs)) if bulk else client.get(route)
        form = confirmation(preview, route)
        middleware = app.middleware_stack
        while not isinstance(middleware, BrowserAuth):
            middleware = middleware.app
        admission, busy, reliable = ObservedLock(), ObservedLock(), ObservedLock()
        monkeypatch.setattr(middleware, 'admission', admission)
        monkeypatch.setattr(app.state.pipeline, 'busy', busy)
        monkeypatch.setattr(app.state.reliable, 'lock', reliable)
        before = store.observations(SID, limit=100)
        controls = store.source_control(SID)
        held = [admission, busy, reliable]
        for lock in held:
            lock.acquire()
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.post, route, data=form)
            try:
                for lock in (admission, busy, reliable):
                    assert lock.waiting.wait(3), 'Deletion must wait for each dependency'
                    assert not pending.done()
                    assert store.observations(SID, limit=100) == before
                    assert client.get('/api/v1/health').status_code == 200
                    if lock is reliable and changed_while_waiting:
                        with store.connection() as db:
                            db.execute('UPDATE frames SET evidence_png=NULL WHERE source_id=?', (SID,))
                        before = store.observations(SID, limit=100)
                    lock.release()
                    held.remove(lock)
            finally:
                for lock in held:
                    lock.release()
            response = pending.result(timeout=5)
        assert response.status_code == 200
        assert all(not lock.locked() for lock in (admission, busy, reliable))
        assert store.source_control(SID) == controls
        if changed_while_waiting:
            assert 'Recorded data changed. Review the updated counts' in response.text
            assert store.observations(SID, limit=100) == before
            assert client.post(route, data=confirmation(response, route)).status_code == 200
        remaining = store.observations(SID, limit=100)
        assert not any(o['question_id'] in {qid for _, qid in pairs} for o in remaining)
        assert any(o['question_id'] == 'brightness' for o in remaining)
