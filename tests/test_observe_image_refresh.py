import shutil
import subprocess

import pytest

from vop.dashboard import OBSERVE_IMAGES_JS


def test_refresh_updates_frame_caption_and_ring_without_capturing():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for the browser-script unit check')
    harness = r"""
const assert = require('node:assert/strict');
let requestCount = 0, writes = 0, next = {status:200, frame:'first', monitoring:'true'};
const image = {hidden:true, naturalWidth:0, removeAttribute() { this.src = ''; }};
Object.defineProperty(image, 'src', {set(value) { this.url = value; writes++; }});
const empty = {hidden:false}, caption = {}, label = {};
const card = {dataset:{imageUrl:'/ui/live-preview/fixture', frame:''},
  classList:{toggle(name,value) { card.monitoring = value; }},
  querySelector(selector) { return selector === 'img' ? image : selector === '[data-preview-empty]' ? empty : selector === '[data-preview-caption]' ? caption : label; }};
global.document = {hidden:false, querySelectorAll() { return [card]; }};
global.setTimeout = (callback, delay) => { assert.equal(delay, 5000); };
global.fetch = async (url, options) => {
  assert.equal(options.method, 'HEAD'); assert.equal(options.cache, 'no-store'); requestCount++;
  const headers = {'X-VOP-Monitoring':next.monitoring, 'X-VOP-Frame-Id':next.frame,
    'X-VOP-Captured-At':'2026-10-22T10:00:00+00:00', 'X-VOP-Preview-Kind':'temporary'};
  return {ok:true, status:next.status, headers:{get(key) { return headers[key]; }}};
};
"""
    checks = r"""
(async () => {
  await new Promise(setImmediate);
  assert.equal(card.monitoring, true); assert.equal(label.textContent, 'Monitoring');
  assert.match(image.url, /frame=first/); image.onload(); image.naturalWidth = 300;
  assert.equal(image.hidden, false); assert.equal(empty.hidden, true);
  const previous = writes;
  await refreshPreview(card); assert.equal(writes, previous);
  next = {status:200, frame:'second', monitoring:'false'};
  await refreshPreview(card);
  assert.equal(card.monitoring, false); assert.equal(label.textContent, 'Paused');
  assert.match(image.url, /frame=second/); assert.match(caption.textContent, /Latest image:/);
  next.status = 204; await refreshPreview(card);
  assert.equal(image.hidden, true); assert.equal(empty.hidden, false);
  const count = requestCount; document.hidden = true; await refreshPreviews();
  assert.equal(requestCount, count);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run([node], input='\n'.join((harness, OBSERVE_IMAGES_JS, checks)), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
