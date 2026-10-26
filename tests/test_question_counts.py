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
        steps = 0
        def budget():
            nonlocal steps
            steps += 100
            return int(steps > 50000 + extra_runs * 500)
        db.set_progress_handler(budget, 100)
        counts = question_counts(db, SID, 'red_square')
        db.set_progress_handler(None, 0)
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
        monkeypatch.setattr('vop.removal.question_counts', forbidden)
        page = client.get('/?view=questions')
        assert page.status_code == 200
        assert 'Delete question' in page.text and 'Front door' in page.text


def test_counts_fragment_wait_does_not_block_configuration_or_health(app, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from bs4 import BeautifulSoup
    from vop.removal import question_counts as original

    setup_history(app)
    entered, release = Event(), Event()
    def slow(db, sid, qid):
        entered.set()
        assert release.wait(5), 'Test must release the artificial count workload'
        return original(db, sid, qid)
    with TestClient(app) as client:
        login(client)
        monkeypatch.setattr('vop.removal.question_counts', slow)
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(client.get, '/ui/question-counts?source='+SID)
            try:
                assert entered.wait(3)
                page = client.get('/?view=questions')
                assert page.status_code == 200 and 'Loading recorded data counts' in page.text
                assert client.get('/api/v1/health').status_code == 200
                assert not pending.done()
            finally:
                release.set()
            response = pending.result(timeout=5)
        assert response.status_code == 200
        cells = BeautifulSoup(response.text, 'html.parser').select('[data-count]')
        assert len(cells) == 12
        assert all(c['data-source'] == SID for c in cells)
        assert client.get('/ui/question-counts?source=missing').status_code == 400
        script = client.get('/ui/question-counts.js')
        assert script.status_code == 200
        assert "script-src 'self'" in script.headers['content-security-policy']
        client.post('/ui/mode', data={'csrf':BeautifulSoup(page.text,'html.parser').select_one('[name=csrf]')['value'], 'mode':'view'})
        assert client.get('/ui/question-counts', follow_redirects=False).status_code == 303


def test_count_lookup_indexes_exist_after_reopen(app):
    from vop.storage import Store
    reopened = Store(app.state.store.path)
    with reopened.connection() as db:
        indexes = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {'observations_count_lookup','frames_with_evidence','observations_run'} <= indexes


def test_count_script_updates_cells_preserves_selection_and_offers_retry():
    import json
    import shutil
    import subprocess
    from vop.removal import QUESTION_COUNTS_JS
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is only needed for this JavaScript regression check')
    script = r'''
const assert = require('node:assert/strict');
(async () => {
  const status = {textContent:''}, retry = {hidden:true, addEventListener:(_,fn) => retry.click=fn};
  const checkbox = {checked:true};
  let calls=0, mode='ok', timer;
  const target = {dataset:{source:'fixture',question:'q',count:'answers'},childNodes:['Loading'],
    replaceChildren(...nodes) {this.childNodes=nodes;}};
  const incoming = {dataset:{...target.dataset},childNodes:['123']};
  const list = {dataset:{countsUrl:'/ui/question-counts?source=fixture'},
    querySelector: selector => selector==='[data-counts-status]' ? status : retry,
    querySelectorAll: () => [target]};
  global.document = {querySelector:() => list};
  global.setTimeout = fn => {timer=fn;return 1;};
  global.clearTimeout = () => {};
  global.DOMParser = class {parseFromString() {return {querySelectorAll:() => mode==='missing' ? [] : [incoming]};}};
  global.fetch = async (url, options) => {
    calls++; assert.equal(url,list.dataset.countsUrl); assert.equal(options.headers.Accept,'text/html');
    if (mode==='error') return {ok:false};
    if (mode==='hang') return new Promise((_,reject) => options.signal.addEventListener('abort',() => reject(new Error('timeout'))));
    return {ok:true,redirected:false,text:async () => '<div>counts</div>'};
  };
  new Function(SOURCE)();
  await new Promise(setImmediate);
  assert.equal(calls,1); assert.deepEqual(target.childNodes,['123']); assert.equal(checkbox.checked,true);
  assert.match(status.textContent,/counts loaded/); assert.equal(retry.hidden,true);
  mode='error'; await retry.click(); assert.equal(retry.hidden,false); assert.match(status.textContent,/Try again/);
  mode='missing'; await retry.click(); assert.equal(retry.hidden,false); assert.deepEqual(target.childNodes,['123']);
  mode='hang'; const pending=retry.click(); await new Promise(setImmediate); timer(); await pending;
  assert.equal(retry.hidden,false);
  mode='ok'; await retry.click(); assert.equal(retry.hidden,true);
  document.querySelector=() => null; const before=calls; new Function(SOURCE)(); assert.equal(calls,before);
})().catch(error => {console.error(error);process.exitCode=1;});
'''.replace('SOURCE', json.dumps(QUESTION_COUNTS_JS))
    result = subprocess.run([node,'-e',script],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stderr
