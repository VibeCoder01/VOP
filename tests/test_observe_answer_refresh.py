import shutil
import subprocess

import pytest

from vop.dashboard import OBSERVE_ANSWERS_JS


def test_open_answers_poll_without_reloading_or_touching_closed_panels():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the browser-script unit check')
    harness = r"""
const assert = require('node:assert/strict');
let calls = 0, release, fail, listener, scheduled;
const content = {innerHTML:'old answers'};
const panel = {open:false, dataset:{answerUrl:'/fixture'},
  querySelector() { return content; }, addEventListener(event, callback) { listener = callback; }};
global.document = {hidden:false, querySelectorAll() { return [panel]; }};
global.setTimeout = (callback, delay) => { assert.equal(delay,200); scheduled=callback; };
global.fetch = (url, options) => {
  calls++; assert.equal(url,'/fixture'); assert.equal(options.cache,'no-store');
  assert.deepEqual(options.headers, panel.dataset.etag ? {'If-None-Match':panel.dataset.etag} : {});
  return new Promise((resolve,reject) => { release=resolve; fail=reject; });
};
const response = (status, html, tag='new') => ({status, text:async()=>html, headers:{get(){return tag;}}});
"""
    checks = r"""
(async () => {
  await new Promise(setImmediate); assert.equal(calls,0);
  panel.open=true; listener(); assert.equal(calls,1);
  await refreshAnswers(panel); assert.equal(calls,1); // No overlapping requests.
  assert.equal(content.innerHTML,'old answers');
  release(response(200,'fresh answers')); await new Promise(setImmediate);
  assert.equal(content.innerHTML,'fresh answers'); assert.equal(panel.open,true);
  assert.equal(panel.dataset.etag,'new');
  const unchanged=refreshAnswers(panel); release(response(304)); await unchanged;
  assert.equal(content.innerHTML,'fresh answers');
  const pending=refreshAnswers(panel); panel.open=false;
  release(response(200,'must not replace closed panel','closed')); await pending;
  assert.equal(content.innerHTML,'fresh answers'); assert.equal(panel.dataset.etag,'new');
  const n=calls; await refreshAnswers(panel); assert.equal(calls,n);
  panel.open=true; document.hidden=true; await refreshAnswers(panel); assert.equal(calls,n);
  document.hidden=false;
  const failed=refreshAnswers(panel); fail(new Error('offline')); await failed;
  assert.equal(content.innerHTML,'fresh answers');
  const retry=refreshAnswers(panel); release(response(200,'recovered','recovered')); await retry;
  assert.equal(content.innerHTML,'recovered'); assert.equal(panel.dataset.etag,'recovered');
})().catch(error => { console.error(error); process.exitCode=1; });
"""
    result = subprocess.run([node], input='\n'.join((harness, OBSERVE_ANSWERS_JS, checks)), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
