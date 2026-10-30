import json
import shutil
import subprocess

import pytest
from bs4 import BeautifulSoup
from starlette.testclient import TestClient

from test_phase4_worker import app, login, VIEWER
from vop.dashboard import TRENDS_REFRESH_JS, CSS


def test_only_trends_loads_authenticated_refresh_script_without_capture(app, monkeypatch):
    def fail(*args):
        pytest.fail('Refreshing a page must not acquire an image')
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', fail)
    before = app.state.store.source_control('synthetic-scene')
    with TestClient(app) as client:
        assert client.get('/ui/trends-refresh.js').status_code == 401
        assert client.get('/?view=metrics', headers={'Accept':'*/*'}, follow_redirects=False).status_code == 401
        login(client)
        for headers in ({}, {'Authorization': 'Bearer ' + VIEWER}):
            page = client.get('/?view=metrics&source=synthetic-scene&timezone=UTC', headers=headers)
            assert page.status_code == 200
            assert '/ui/trends-refresh.js' in page.text
            assert 'trends-workspace' in BeautifulSoup(page.text, 'html.parser').select_one('main')['class']
            assert '.trends-workspace{animation:none}' in CSS
            assert 'Auto refresh: every 00:00:10.0' in page.text
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
let timer, delay, reloads=0, updates=0, requests=0, busy=false;
const filters={values:[['view','metrics'],['source','fixture'],['source','garden'],['from','2026-10-01'],['through','2026-10-31']],contains:x=>x==='filter'};
const status={textContent:''};
global.document={hidden:false,activeElement:null,querySelector:s=>s==='form.filters'?filters:status};
global.FormData=class {constructor(form){this.form=form;}[Symbol.iterator](){return this.form.values[Symbol.iterator]();}};
global.location={href:'http://127.0.0.1/?view=metrics&source=fixture&source=garden&from=2026-10-01&through=2026-10-31',reload:()=>reloads++};
global.setInterval=(fn,ms)=>{timer=fn;delay=ms;};global.window=global;
global.vopTrends={busy:()=>busy,update:()=>{updates++;return true;}};
global.DOMParser=class{parseFromString(){return {querySelector:()=>status};}};
const good=()=>({ok:true,redirected:false,text:async()=>'<offline-fixture>'});
global.fetch=async(url,options)=>{requests++;assert.equal(url,location.href);assert.equal(options.headers.Accept,'*/*');return good();};
(async()=>{
new Function(SOURCE)();assert.equal(delay,10000);
await timer();assert.equal(updates,1);assert.equal(reloads,0);
document.hidden=true;await timer();assert.equal(updates,1);
document.hidden=false;document.activeElement='filter';await timer();assert.equal(updates,1);
document.activeElement=null;filters.values[1][1]='unsaved';await timer();assert.equal(updates,1);
filters.values[1][1]='fixture';await timer();assert.equal(updates,2);
busy=true;await timer();assert.equal(updates,2);busy=false;
// User starts navigating while a response arrives: discard the response.
fetch=async()=>{busy=true;return good();};await timer();assert.equal(updates,2);busy=false;
// Only one request at a time, even if rendering a large date range takes time.
let finish;fetch=()=>new Promise(resolve=>{finish=resolve;requests++;});
const pending=timer(),before=requests;await timer();assert.equal(requests,before);
finish(good());await pending;assert.equal(updates,3);
fetch=async()=>({ok:true,redirected:true});await timer();assert.equal(updates,3);assert.match(status.textContent,/try again/);
fetch=async()=>good();vopTrends.update=()=>false;await timer();assert.match(status.textContent,/setup changed/);
vopTrends.update=()=>{updates++;return true;};await timer();assert.equal(status.textContent,'');
fetch=async()=>({ok:false});await timer();assert.match(status.textContent,/try again/);
window.vopSessionExpired=true;await timer();assert.equal(updates,4);assert.equal(reloads,0);
// Expiry during a fetch must not patch the login response into Trends.
window.vopSessionExpired=false;fetch=async()=>{window.vopSessionExpired=true;return good();};await timer();assert.equal(updates,4);
timer=null;document.querySelector=()=>null;new Function(SOURCE)();assert.equal(timer,null);
})().catch(error => {console.error(error); process.exitCode=1;});
'''.replace('SOURCE', json.dumps(TRENDS_REFRESH_JS))
    result = subprocess.run([shutil.which('node'), '-e', script], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
