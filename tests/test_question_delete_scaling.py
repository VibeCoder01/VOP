"""Bound deletion work on disposable synthetic histories; no real images/cameras."""
import json
from time import perf_counter

from starlette.testclient import TestClient
import pytest

from test_removed_question_bulk import app, no_workers, setup_history, login, SID
from vop.history_deletion import question_selection, delete_question_data
from vop.storage import dumps


def seed_runs(db, count, shared):
    template = db.execute('SELECT id,result_json FROM runs WHERE source_id=? LIMIT 1', (SID,)).fetchone()
    qids = ['red_square', 'background'] if shared else ['red_square']
    rows = db.execute('SELECT * FROM observations WHERE run_id=?', (template['id'],)).fetchall()
    body = json.loads(template['result_json'])
    body['answers'] = [a for a in body['answers'] if a['question_id'] in qids]
    for i in range(count):
        run_id = f'scale-run-{i}'
        db.execute('INSERT INTO runs SELECT ?,source_id,NULL,processed_at_utc,? FROM runs WHERE id=?',
                   (run_id, dumps(body), template['id']))
        for row in rows:
            if row['question_id'] not in qids:
                continue
            db.execute("""INSERT INTO observations(id,run_id,source_id,question_id,question_version,captured_at_utc,processed_at_utc,status,normalised_state,answer_json)
                          VALUES(?,?,?,?,?,?,?,?,?,?)""", (f"scale-answer-{i}-{row['question_id']}", run_id,
                       row['source_id'],row['question_id'],row['question_version'],row['captured_at_utc'],row['processed_at_utc'],
                       row['status'],row['normalised_state'],row['answer_json']))


@pytest.mark.parametrize('extra_runs', [500, 1500])
@pytest.mark.parametrize('shared', [False, True])
def test_question_purge_has_bounded_sql_work_and_preserves_other_answers(app, extra_runs, shared):
    setup_history(app)
    store = app.state.store
    with store.connection() as db:
        seed_runs(db, extra_runs, shared)
        other = [tuple(r) for r in db.execute("SELECT id,answer_json FROM observations WHERE source_id=? AND question_id!='red_square' ORDER BY id", (SID,))]
        steps = 0
        def budget():
            nonlocal steps
            steps += 100
            return int(steps > 100000 + extra_runs * 1000)
        db.set_progress_handler(budget, 100)
        started = perf_counter()
        chosen = question_selection(db, SID, 'red_square')
        delete_question_data(db, chosen)
        elapsed = perf_counter() - started
        db.set_progress_handler(None, 0)
        print(f'Synthetic purge: shared={shared}, runs={extra_runs}, VM steps={steps}, seconds={elapsed:.3f}')
        assert not db.execute("SELECT 1 FROM observations WHERE source_id=? AND question_id='red_square'", (SID,)).fetchone()
        remaining = [tuple(r) for r in db.execute("SELECT id,answer_json FROM observations WHERE source_id=? ORDER BY id", (SID,))]
        # Only raw details may be cleared from surviving normalized answers.
        normalize = lambda rows: {oid:{k:v for k,v in json.loads(answer).items() if k not in ('raw_provider_fields','usage')} for oid,answer in rows}
        assert normalize(remaining) == normalize(other)
        assert db.execute("SELECT count(*) FROM runs WHERE id LIKE 'scale-run-%'").fetchone()[0] == (extra_runs if shared else 0)
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_delete_preview_uses_metadata_without_loading_full_results(app, monkeypatch):
    setup_history(app)
    from vop.history_deletion import question_selection as original
    calls = []
    def metadata(db, sid, qid, *, include_runs=True):
        assert include_runs is False, 'Confirmation preview must not load every raw capture'
        sql = []
        db.set_trace_callback(sql.append)
        try:
            chosen = original(db, sid, qid, include_runs=include_runs)
        finally:
            db.set_trace_callback(None)
        assert not chosen['runs']
        assert not any('result_json' in statement or 'answer_json' in statement for statement in sql)
        calls.append(qid)
        return chosen
    monkeypatch.setattr('vop.removal.question_selection', metadata)
    with TestClient(app) as client:
        login(client)
        response = client.get(f'/ui/questions/{SID}/red_square/delete')
        assert response.status_code == 200 and 'Recorded data' in response.text
        assert calls == ['red_square']
