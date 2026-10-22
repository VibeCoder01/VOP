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
let requestCount = 0, leaseCount = 0, writes = 0, next = {status:200, frame:'first', monitoring:'true'};
let finishDecode, failDecode;
global.Image = class {
  constructor() { this.hidden = false; this.naturalWidth = 300; this.alt = 'Camera preview'; }
  set src(value) { this.url = value; writes++; }
  removeAttribute() { this.url = ''; }
  decode() { return new Promise((resolve, reject) => { finishDecode = resolve; failDecode = reject; }); }
  replaceWith(replacement) { image = replacement; }
};
let image = new Image(); image.hidden = true; image.naturalWidth = 0;
const empty = {hidden:false}, caption = {}, label = {};
const card = {dataset:{imageUrl:'/ui/live-preview/fixture', frame:''},
  classList:{toggle(name,value) { card.monitoring = value; }},
  querySelector(selector) { return selector === 'img' ? image : selector === '[data-preview-empty]' ? empty : selector === '[data-preview-caption]' ? caption : label; }};
global.document = {hidden:false, querySelectorAll() { return [card]; }};
global.setTimeout = (callback, delay) => { assert.equal(delay, 200); };
global.fetch = async (url, options) => {
  if (options.method === 'POST') {
    assert.equal(url, '/fixture/keepalive'); assert.equal(options.body.get('csrf'), 'fixture-csrf'); leaseCount++;
    return {ok:true, status:202};
  }
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
  assert.equal(image.hidden, true); assert.equal(card.dataset.frame, '');
  finishDecode(); await new Promise(setImmediate);
  assert.match(image.url, /frame=first/);
  assert.equal(image.hidden, false); assert.equal(empty.hidden, true);
  const previous = writes;
  await refreshPreview(card); assert.equal(writes, previous);
  next = {status:200, frame:'second', monitoring:'false'};
  const oldImage = image;
  const pending = refreshPreview(card); await new Promise(setImmediate);
  assert.equal(image, oldImage); assert.equal(image.hidden, false);
  assert.equal(card.dataset.frame, 'first');
  finishDecode(); await pending;
  assert.notEqual(image, oldImage);
  assert.equal(card.monitoring, false); assert.equal(label.textContent, 'Paused');
  assert.match(image.url, /frame=second/); assert.match(caption.textContent, /Latest image:/);
  const displayed = image;
  next.frame = 'failed-frame';
  const failed = refreshPreview(card); await new Promise(setImmediate);
  failDecode(new Error('temporary image failure')); await failed;
  assert.equal(image, displayed); assert.equal(card.dataset.frame, 'second');
  // The failed frame is retried and only marked displayed after decoding.
  const retry = refreshPreview(card); await new Promise(setImmediate);
  finishDecode(); await retry; assert.equal(card.dataset.frame, 'failed-frame');
  card.dataset.leaseUrl = '/fixture/keepalive'; card.dataset.csrf = 'fixture-csrf';
  await refreshPreview(card); assert.equal(leaseCount, 1);
  await refreshPreview(card); assert.equal(leaseCount, 1);
  card.dataset.renewAt = '0'; await refreshPreview(card); assert.equal(leaseCount, 2);
  next.status = 204; await refreshPreview(card);
  assert.equal(image.hidden, true); assert.equal(empty.hidden, false);
  const count = requestCount; document.hidden = true; await refreshPreviews();
  assert.equal(requestCount, count); assert.equal(leaseCount, 2);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run([node], input='\n'.join((harness, OBSERVE_IMAGES_JS, checks)), capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
