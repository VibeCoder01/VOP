"""Native question-deletion progress enhancement; synthetic data only."""
import shutil
import subprocess

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_removed_question_bulk import app, no_workers, setup_history, login, selection, confirmation, SID, BULK
from vop.removal import QUESTION_DELETE_JS


@pytest.mark.parametrize('bulk', [False, True])
def test_confirmation_has_closed_accessible_progress_dialog_and_native_form(app, bulk):
    setup_history(app)
    with TestClient(app) as client:
        assert client.get('/ui/question-delete.js').status_code == 401
        csrf = login(client)
        route = BULK if bulk else f'/ui/questions/{SID}/red_square/delete'
        response = client.post(route, data=selection(csrf)) if bulk else client.get(route)
        soup = BeautifulSoup(response.text, 'html.parser')
        form = soup.select_one('form[data-question-delete]')
        assert form['method'] == 'post' and form['action'] == route
        assert form.select_one('[name=csrf]')['value'] == csrf
        assert form.select_one('[name=expected_data]')['value']
        dialog = soup.select_one('dialog[data-question-delete-progress]')
        assert 'open' not in dialog.attrs
        assert soup.find(id=dialog['aria-labelledby']).text == 'Deleting questions'
        assert soup.find(id=dialog['aria-describedby'])
        progress = dialog.find('progress')
        assert 'value' not in progress.attrs  # Honest indeterminate progress, no invented percentage.
        assert progress['aria-label']
        assert 'Keep this page open' in dialog.text
        assert soup.select_one('script[src="/ui/question-delete.js"][defer]')
        assert client.get('/ui/question-delete.js').text == QUESTION_DELETE_JS
        # The native confirmation/result route still completes without JavaScript.
        result = client.post(route, data=confirmation(response, route), follow_redirects=False)
        assert result.status_code == 303
        assert not any(q['spec'].question_id == 'red_square' for q in app.state.store.questions(SID))


def test_progress_preserves_native_submit_blocks_duplicates_and_resets_on_back():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the browser-script unit check')
    harness = r"""
const assert = require('node:assert/strict');
let submit, cancel, pageshow, shown = 0, closed = 0;
const button = {textContent:'Delete question and data', removeAttribute() {}};
const form = {attrs:{}, querySelectorAll() { return [button]; },
  setAttribute(name,value) { this.attrs[name]=value; }, removeAttribute(name) { delete this.attrs[name]; },
  addEventListener(name, callback) { assert.equal(name,'submit'); submit=callback; }};
const dialog = {open:false, showModal() { shown++; this.open=true; }, close() { closed++; this.open=false; },
  addEventListener(name, callback) { assert.equal(name,'cancel'); cancel=callback; }};
global.document = {querySelector(selector) { return selector === '[data-question-delete]' ? form : dialog; }};
global.window = {addEventListener(name, callback) { assert.equal(name,'pageshow'); pageshow=callback; }};
function event(prevented=false) { return {defaultPrevented:prevented, preventDefault(){this.defaultPrevented=true;}}; }
"""
    checks = r"""
assert.equal(shown,0);
submit(event(true)); assert.equal(shown,0); // Respect prior validation or cancellation.
const first=event(); submit(first);
assert.equal(first.defaultPrevented,false); // Browser submits the unchanged native form.
assert.equal(shown,1); assert.equal(form.attrs['aria-busy'],'true');
const duplicate=event(); submit(duplicate);
assert.equal(duplicate.defaultPrevented,true); assert.equal(shown,1);
const escape=event(); cancel(escape);
assert.equal(escape.defaultPrevented,true); assert.equal(dialog.open,true);
pageshow({persisted:false}); assert.equal(dialog.open,true);
button.textContent='Working…'; pageshow({persisted:true});
assert.equal(closed,1); assert.equal(dialog.open,false); assert.equal(form.attrs['aria-busy'],undefined);
assert.equal(button.textContent,'Delete question and data');
const retry=event(); submit(retry);
assert.equal(retry.defaultPrevented,false); assert.equal(shown,2);
"""
    result = subprocess.run([node], input='\n'.join((harness, QUESTION_DELETE_JS, checks)), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    # Older browsers retain the normal form workflow without modal support.
    fallback = harness.replace('showModal() { shown++; this.open=true; },', '')
    result = subprocess.run([node], input='\n'.join((fallback, QUESTION_DELETE_JS, 'assert.equal(submit,undefined);')), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
