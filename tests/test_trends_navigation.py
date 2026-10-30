"""Offline page contracts and native canvas navigation, without a camera/browser session."""
from datetime import datetime, timedelta, timezone
import json
import shutil
import subprocess

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, VIEWER
from vop.trends_ui import SCRIPT, domain


def test_full_time_range_and_viewer_assets_do_not_capture(app, monkeypatch):
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    points = [{'at_utc':(start+timedelta(seconds=i*i)).isoformat(), 'value':bool(i%2), 'gap_before':i==4} for i in range(120)]
    original = app.state.store.summary
    def summary(*args, **kwargs):
        return {**original(*args, **kwargs), 'trend':points}
    monkeypatch.setattr(app.state.store, 'summary', summary)
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', lambda *a: pytest.fail('Page must not capture'))
    with TestClient(app) as client:
        assert client.get('/ui/trends.js').status_code == 401
        headers = {'Authorization':'Bearer '+VIEWER}
        assert client.get('/ui/trends.js', headers=headers).text == SCRIPT
        page = client.get('/?view=metrics&from=2026-10-01&through=2026-10-02', headers=headers)
        assert page.status_code == 200
        doc = BeautifulSoup(page.text, 'html.parser')
        graphs = doc.select('[data-trend]')
        assert len(graphs) == 2
        assert len(doc.select('[data-trend-section]')) == 3
        assert len(doc.select('[data-trend-value]')) == 12
        assert len({(g['data-start'],g['data-end']) for g in graphs}) == 1
        data = json.loads(graphs[0]['data-points'])
        assert len(data) == 120 and data[4][2] == 1
        assert data[2][0]-data[1][0] == 3000  # True timestamp spacing, not sample order.
        assert doc.select_one('[data-trend-lock]')
        assert 'Latest 60 samples' not in page.text
        assert '/ui/trends.js' not in client.get('/', headers=headers).text
    assert app.state.store.health()['observation_count'] == 0


def test_common_domain_and_single_sample_width():
    empty = domain([])
    assert empty[1]-empty[0] == 3600000
    assert domain([[{'at_utc':'2026-10-01T00:00:00Z'}]]) == (1790812800000,1790812801000,1790812800000)
    bounds = domain([[{'at_utc':'2026-10-01T01:00:00+01:00'}],[{'at_utc':'2026-10-02T00:00:00Z'}]])
    assert bounds[1]-bounds[0] == 86400000


@pytest.mark.skipif(not shutil.which('node'), reason='Node is needed for offline navigation verification')
def test_pan_zoom_sync_restore_gaps_and_visible_slice():
    harness = r'''
const assert=require('node:assert/strict');
let saved={},clock=0;Date.now=()=>clock;
const ctx=()=>new Proxy({calls:[],setTransform(){this.calls=[];}},{get(o,k){return k in o?o[k]:(...a)=>o.calls.push([k,...a]);}});
class El {
 constructor(){this.events={};this.disabled=true;this.checked=false;this.scrollLeft=0;this.clientWidth=680;this.hidden=false;this.attrs={};}
 addEventListener(k,fn){this.events[k]=fn;}
 fire(k,e={}){this.events[k]?.({preventDefault(){},...e});}
 setAttribute(k,v){this.attrs[k]=v;}
 getBoundingClientRect(){return {width:680,left:0};}
 setPointerCapture(){}
}
function root(key,points,end=100000){
 const r=new El();r.dataset={trend:key,points:JSON.stringify(points),start:'0',end:String(end),latest:String(end),zone:'UTC'};r.parts={};
 for(const key of ['canvas','scroll','track','zoom','readout','window','scale','earlier','later','in','out','fit','latest','fallback'])r.parts[key]=new El();
 r.parts.canvas.ctx=ctx();r.parts.canvas.getContext=()=>r.parts.canvas.ctx;
 r.querySelector=s=>r.parts[s.slice(12,-1)];r.querySelectorAll=()=>Object.values(r.parts);return r;
}
const a=root('a',[[0,0,0],[10000,1,0],[30000,0,1],[100000,1,0]]);
const b=root('b',[[0,1,0],[100000,0,0]]);
let roots=[a,b],lock=new El();
global.document={querySelectorAll:()=>roots,querySelector:s=>s==='[data-trend-lock]'?lock:null};
global.location={pathname:'/',search:'?view=metrics'};
global.sessionStorage={getItem:k=>saved[k],setItem:(k,v)=>saved[k]=v};
global.window=global;global.addEventListener=()=>{};global.requestAnimationFrame=fn=>fn();
new Function(SOURCE)();
const state=key=>{vopTrends.save();return JSON.parse(saved['vop-trend-view']).views[key];};
const incomingDoc=incoming=>({querySelectorAll:s=>s==='[data-trend]'?incoming:[]});
assert.equal(a.parts.canvas.hidden,false);assert.equal(a.parts.fallback.hidden,true);
// Actual timestamps position 10 seconds at 10% of the plot, not one third.
let lines=a.parts.canvas.ctx.calls.filter(c=>c[0]==='lineTo');
assert.ok(lines.some(c=>Math.abs(c[1]-109.6)<.01));
// gap_before moves the pen instead of joining across unobserved time.
assert.ok(a.parts.canvas.ctx.calls.some(c=>c[0]==='moveTo'&&Math.abs(c[1]-232.8)<.01));
a.parts.in.fire('click');assert.equal(state('a').span,50000);assert.equal(state('b').span,100000);
assert.equal(vopTrends.busy(),true);clock=2000;assert.equal(vopTrends.busy(),false);
lock.checked=true;lock.fire('change');assert.deepEqual(state('a'),state('b'));
a.parts.earlier.fire('click');assert.equal(state('a').start,0);assert.deepEqual(state('a'),state('b'));
a.parts.scroll.scrollLeft=340;a.parts.scroll.fire('scroll');assert.equal(state('a').start,25000);assert.deepEqual(state('a'),state('b'));
// Programmatic scroll notifications cannot shift the synchronized timestamp window.
b.parts.scroll.fire('scroll');assert.deepEqual(state('a'),state('b'));
lock.checked=false;lock.fire('change');a.parts.later.fire('click');assert.equal(state('a').start,50000);assert.equal(state('b').start,25000);
a.parts.canvas.fire('pointerdown',{button:0,clientX:100,pointerId:1});clock+=5000;assert.equal(vopTrends.busy(),true);
a.parts.canvas.fire('pointercancel');clock+=2000;assert.equal(vopTrends.busy(),false);
a.parts.latest.fire('click');assert.equal(state('a').follow,true);assert.equal(state('b').follow,false);
// Periodic updates repaint the same canvas, without replacing controls or scrolling the page.
const canvas=a.parts.canvas;global.scrollY=1234;
function section(key,text){const value={textContent:text,style:{},getBoundingClientRect:()=>({height:76})};
 const summary={childNodes:[text],contains:()=>false,replaceChildren(...nodes){this.childNodes=nodes;}};
 return {dataset:{trendSection:key},value,summary,querySelectorAll:()=>[value],querySelector:()=>summary};}
const live=section('a','No interval data'),fresh=section('a','12.0%');
const originalQuery=document.querySelectorAll;document.querySelectorAll=s=>s==='[data-trend]'?roots:[live];
const nextRoots=[root('a',[[0,0,0],[120000,1,0]],120000),root('b',[[0,1,0],[120000,0,0]],120000)];
assert.equal(vopTrends.update({querySelectorAll:s=>s==='[data-trend]'?nextRoots:[fresh]}),true);
assert.equal(state('a').start,70000);assert.equal(state('b').start,25000);assert.equal(a.parts.canvas,canvas);assert.equal(scrollY,1234);
assert.equal(live.value.textContent,'12.0%');assert.equal(live.value.style.minHeight,'76px');assert.deepEqual(live.summary.childNodes,['12.0%']);
assert.equal(vopTrends.update(incomingDoc([root('changed-question',[])])),false);assert.equal(a.parts.canvas,canvas);
document.querySelectorAll=originalQuery;
// Refresh keeps historical absolute windows and follows the latest only when requested.
roots=[root('a',[[0,0,0],[120000,1,0]],120000),root('b',[[0,1,0],[120000,0,0]],120000)];lock=new El();
new Function(SOURCE)();assert.equal(state('a').start,70000);assert.equal(state('b').start,25000);
roots[1].parts.fit.fire('click');assert.equal(state('b').span,120000);
// A long series is retained, but zoomed rendering only visits the visible slice.
roots=[root('dense',Array.from({length:20000},(_,i)=>[i*5,i%2,0]))];lock=new El();saved={};new Function(SOURCE)();
roots[0].parts.zoom.value=10;roots[0].parts.zoom.fire('input');
assert.ok(roots[0].parts.canvas.ctx.calls.filter(c=>c[0]==='lineTo').length<30);
// A date filter can extend into the future: Latest must show recorded data, not midnight.
roots=[root('future',[[0,0,0],[30000,1,0]])];roots[0].dataset.latest='30000';saved={};lock=new El();new Function(SOURCE)();
roots[0].parts.zoom.value=3;roots[0].parts.zoom.fire('input');roots[0].parts.latest.fire('click');
assert.equal(state('future').start+state('future').span,30000);
// An initially empty graph gets its first result through the same update path.
roots=[root('empty',[])];saved={};lock=new El();new Function(SOURCE)();document.querySelectorAll=s=>s==='[data-trend]'?roots:[];
const emptyCanvas=roots[0].parts.canvas;
assert.equal(vopTrends.update(incomingDoc([root('empty',[[0,1,0],[100000,0,0]])])),true);
assert.equal(roots[0].parts.canvas,emptyCanvas);assert.ok(emptyCanvas.ctx.calls.some(c=>c[0]==='arc'));
'''.replace('SOURCE', json.dumps(SCRIPT))
    result = subprocess.run([shutil.which('node')], input=harness, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
