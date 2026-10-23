"""Question listing must not build destructive previews or scan once per capture."""
import pytest
from starlette.testclient import TestClient

from test_removed_question_bulk import app, no_workers, setup_history, login, remove, SID
from vop.history_deletion import question_counts, question_selection


@pytest.mark.parametrize('extra_runs', [1, 1000])
def test_question_counts_use_fixed_queries_without_result_payloads(app, extra_runs):
    setup_history(app)
    with app.state.store.connection() as db:
        baseline = question_counts(db, SID, 'red_square')
        assert baseline == question_selection(db, SID, 'red_square')['counts']
        run = db.execute('SELECT id FROM runs WHERE source_id=? LIMIT 1', (SID,)).fetchone()[0]
        templates = db.execute('SELECT id FROM observations WHERE run_id=? AND question_id IN (?,?)',
                               (run, 'red_square', 'background')).fetchall()
        assert len(templates) == 2
        for i in range(extra_runs):
            rid = f'extra-run-{i}'
            db.execute('INSERT INTO runs SELECT ?,source_id,NULL,processed_at_utc,result_json FROM runs WHERE id=?', (rid, run))
            for j, template in enumerate(templates):
                db.execute('''INSERT INTO observations(id,run_id,source_id,question_id,question_version,captured_at_utc,processed_at_utc,status,normalised_state,answer_json)
                              SELECT ?,?,source_id,question_id,question_version,captured_at_utc,processed_at_utc,status,normalised_state,answer_json FROM observations WHERE id=?''',
                           (f'extra-answer-{i}-{j}', rid, template['id']))
        statements = []
        db.set_trace_callback(statements.append)
        counts = question_counts(db, SID, 'red_square')
        db.set_trace_callback(None)
        assert len(statements) == 4
        assert not any('result_json' in sql or 'answer_json' in sql for sql in statements)
        assert counts == {**baseline, 'answers':baseline['answers']+extra_runs,
                          'other_answers':baseline['other_answers']+extra_runs}


def test_questions_listing_does_not_build_deletion_previews(app, monkeypatch):
    setup_history(app)
    with TestClient(app) as client:
        csrf = login(client)
        remove(client, csrf)
        def forbidden(*_):
            pytest.fail('Listing must not build a full deletion preview')
        monkeypatch.setattr('vop.removal.question_selection', forbidden)
        page = client.get('/?view=questions')
        assert page.status_code == 200
        assert 'Delete question' in page.text and 'Front door' in page.text
