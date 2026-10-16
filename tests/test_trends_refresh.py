import json
import shutil
import subprocess

import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, VIEWER
from vop.dashboard import TRENDS_REFRESH_JS


def test_only_trends_loads_authenticated_refresh_script_without_capture(app, monkeypatch):
    def fail(*args):
        pytest.fail('Refreshing a page must not acquire an image')
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', fail)
    before = app.state.store.source_control('synthetic-scene')
    with TestClient(app) as client:
        assert client.get('/ui/trends-refresh.js').status_code == 401
        login(client)
        for headers in ({}, {'Authorization': 'Bearer ' + VIEWER}):
            page = client.get('/?view=metrics&source=synthetic-scene&timezone=UTC', headers=headers)
            assert page.status_code == 200
            assert '/ui/trends-refresh.js' in page.text
            assert 'Auto refresh: every 10 seconds' in page.text
            assert 'Apply your changes to resume' in page.text
            assert '/ui/trends-refresh.js' not in client.get('/', headers=headers).text
            script = client.get('/ui/trends-refresh.js', headers=headers)
            assert script.status_code == 200 and script.text == TRENDS_REFRESH_JS
            assert "script-src 'self'" in script.headers['content-security-policy']
    assert app.state.store.source_control('synthetic-scene') == before
    assert app.state.store.health()['observation_count'] == 0


@pytest.mark.skipif(not shutil.which('node'), reason='Node is only needed for the JavaScript regression check')
def test_refresh_timer_respects_hidden_tabs_filter_focus_and_unsaved_changes():
    script = r'''
const assert = require('node:assert/strict');
let timer, delay, reloads = 0;
const filters = {values:[['view','metrics'],['source','fixture'],['timezone','UTC']], contains: x => x === 'filter'};
global.document = {hidden:false, activeElement:null, querySelector:() => filters};
global.FormData = class { constructor(form) {this.form = form;} [Symbol.iterator]() {return this.form.values[Symbol.iterator]();} };
global.location = {href:'http://127.0.0.1/?view=metrics&source=fixture&timezone=UTC', reload:() => reloads++};
global.setInterval = (fn, ms) => {timer=fn; delay=ms;};
global.fetch = () => {throw new Error('Refresh must not request a capture or worker operation');};
new Function(SOURCE)();
assert.equal(delay,10000);
timer(); assert.equal(reloads,1);
document.hidden=true; timer(); assert.equal(reloads,1);
document.hidden=false; document.activeElement='filter'; timer(); assert.equal(reloads,1);
document.activeElement=null; filters.values[1][1]='unsaved'; timer(); assert.equal(reloads,1);
filters.values[1][1]='fixture'; timer(); assert.equal(reloads,2);
assert.equal(location.href,'http://127.0.0.1/?view=metrics&source=fixture&timezone=UTC');
timer=null; document.querySelector=() => null; new Function(SOURCE)(); assert.equal(timer,null);
'''.replace('SOURCE', json.dumps(TRENDS_REFRESH_JS))
    result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
