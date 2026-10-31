"""Grid contracts use synthetic frames, offline requests and a fake browser DOM."""
from dataclasses import replace
import json
import shutil
import subprocess
from types import SimpleNamespace
from urllib.parse import parse_qs,urlsplit

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_removed_question_bulk import app,no_workers,login,SID,VIEWER
from vop.dashboard import answer_label
from vop.inputs.sources import capture_inline
from vop.observe_grid import lights,SCRIPT
from fasthtml.common import to_xml


def view(client):
    csrf=login(client)
    client.post('/ui/mode',data={'csrf':csrf,'mode':'view'})
    return csrf


def test_grid_switches_filters_and_normal_camera_link_without_capture(app,monkeypatch):
    monkeypatch.setattr(app.state.pipeline.capture_adapter,'capture',lambda *a:pytest.fail('GET must not capture'))
    monkeypatch.setattr(app.state.pipeline.live_previews,'request',lambda *a:pytest.fail('GET must not start a stream'))
    with TestClient(app) as client:
        assert client.get('/ui/observe-grid.js').status_code==401
        view(client)
        normal=BeautifulSoup(client.get('/').text,'html.parser')
        assert normal.select_one('nav[aria-label="Observe display"]')
        button=normal.find('a',string='Grid View')
        assert button and parse_qs(urlsplit(button['href']).query)['layout']==['grid']
        assert urlsplit(button['href']).fragment=='camera-'+SID
        for mode in ('live','captured'):
            response=client.get('/?layout=grid&images='+mode+'&source='+SID)
            assert response.status_code==200
            doc=BeautifulSoup(response.text,'html.parser')
            assert len(doc.select('[data-grid-camera]'))==1
            assert not doc.select_one('.grid-camera').find('a',string='Full view')
            assert doc.select_one('nav[aria-label="Observe display"]').find('a',string='Full view')
            assert doc.select_one('[data-grid-camera]')['data-mode']==mode
            assert doc.select_one('nav[aria-label="Grid image type"]')
            for link in doc.select('nav[aria-label="Grid image type"] a'):
                assert parse_qs(urlsplit(link['href']).query)['source']==[SID]
            assert '/ui/observe-grid.js' in response.text and '/ui/observe-images.js' not in response.text
            assert 'Show answers' not in response.text and not doc.select('.stats')
            assert len(doc.select('.grid-traffic-light'))==3
        assert client.get('/ui/observe-grid.js').text==SCRIPT
        assert client.get('/?layout=wrong').status_code==400
        viewer={'Authorization':'Bearer '+VIEWER}
        doc=BeautifulSoup(client.get('/?layout=grid',headers=viewer).text,'html.parser')
        assert all(not img.has_attr('src') for img in doc.select('[data-grid-camera] img'))
        assert 'Operator access is required' in doc.get_text()
    assert app.state.store.health()['observation_count']==0


def test_captured_grid_keeps_last_observation_through_pause_and_refuses_older_fallback(app):
    pipeline,store=app.state.pipeline,app.state.store
    frame=capture_inline(pipeline.sources[SID]);pipeline.run(SID,frame)
    store.update_source(SID,enabled=True,retain_evidence=False,sample_interval_seconds=10)
    with TestClient(app) as client:
        view(client)
        before=store.source_control(SID)
        response=client.get('/ui/camera-answers/'+SID+'?grid=1')
        assert response.headers['x-vop-monitoring']=='true'
        assert response.headers['x-vop-processed-frame']==frame.frame_id
        assert client.get('/ui/camera-answers/'+SID+'?grid=1',headers={'If-None-Match':response.headers['etag']}).status_code==304
        normal=client.get('/ui/camera-answers/'+SID)
        assert normal.headers['etag']!=response.headers['etag'] and '<table' in normal.text
        store.update_source(SID,enabled=True,retain_evidence=False,sample_interval_seconds=0)
        pipeline.record_gap(SID)
        paused=client.get('/ui/camera-answers/'+SID+'?grid=1')
        assert paused.headers['x-vop-monitoring']=='false'
        assert paused.headers['x-vop-processed-frame']==frame.frame_id
        doc=BeautifulSoup(client.get('/?layout=grid&images=captured').text,'html.parser')
        card=doc.select_one('[data-grid-camera]')
        assert 'monitoring' not in card['class'] and card.select_one('img')['src'].endswith(frame.frame_id)
        # Normal delete paths clear the transient copy, too.
        pipeline.clear_preview(SID)
        missing=client.get('/ui/camera-answers/'+SID+'?grid=1')
        assert missing.headers['x-vop-processed-url']==''
        assert store.source_control(SID)['retain_evidence']==before['retain_evidence']


def test_captured_grid_does_not_substitute_an_older_saved_image(app):
    pipeline,store=app.state.pipeline,app.state.store
    store.update_source(SID,enabled=True,retain_evidence=True,sample_interval_seconds=0)
    old=capture_inline(pipeline.sources[SID]);pipeline.run(SID,old)
    store.update_source(SID,enabled=True,retain_evidence=False,sample_interval_seconds=0)
    newer=capture_inline(pipeline.sources[SID]);pipeline.run(SID,newer)
    pipeline.latest_preview=None
    assert store.evidence(SID,old.frame_id)
    with TestClient(app) as client:
        view(client)
        response=client.get('/ui/camera-answers/'+SID+'?grid=1')
        assert response.headers['x-vop-processed-url']==''
        doc=BeautifulSoup(client.get('/?layout=grid&images=captured').text,'html.parser')
        assert not doc.select_one('[data-grid-camera] img').has_attr('src')


def test_deleted_latest_capture_gap_is_not_replaced_by_an_older_image(app):
    pipeline,store=app.state.pipeline,app.state.store
    store.update_source(SID,enabled=True,retain_evidence=True,sample_interval_seconds=0)
    old=capture_inline(pipeline.sources[SID]);pipeline.run(SID,old)
    newer=capture_inline(pipeline.sources[SID]);pipeline.run(SID,newer)
    from vop.history_deletion import selection,delete_selected
    with store.connection() as db:
        oid=db.execute('SELECT o.id FROM observations o JOIN runs r ON r.id=o.run_id WHERE r.frame_id=? LIMIT 1',(newer.frame_id,)).fetchone()[0]
        delete_selected(db,selection(db,observation_id=oid))
    pipeline.clear_preview(SID)
    assert store.evidence(SID,old.frame_id)
    with TestClient(app) as client:
        view(client)
        response=client.get('/ui/camera-answers/'+SID+'?grid=1')
        assert response.headers['x-vop-processed-url']==''
        assert 'deleted' in response.headers['x-vop-processed-message']


@pytest.mark.parametrize('kind,value,levels,choices,color',[
    ('binary',True,(),(),'green'),('binary',False,(),(),'red'),('binary',None,(),(),'amber'),
    ('ordinal',0,('Low','Medium','High'),(),'red'),('ordinal',1,('Low','Medium','High'),(),'amber'),
    ('ordinal',2,('Low','Medium','High'),(),'green'),('choice','cat',(),(('cat','A cat'),('dog','A dog')),'green')])
def test_question_light_is_labelled_and_not_a_confidence_score(kind,value,levels,choices,color):
    spec=SimpleNamespace(kind=kind,question_id='question',text='What is visible?',levels=levels,choices=choices)
    html=to_xml(lights([{'spec':spec,'summary':{'latest_value':value},'enabled':True}],answer_label))
    doc=BeautifulSoup(html,'html.parser')
    assert doc.select_one('[data-answer-color]')['data-answer-color']==color
    assert len(doc.select('.grid-answer-lamp'))==3 and len(doc.select('.grid-answer-lamp.lit'))==1
    assert 'What is visible?' in doc.get_text()
    if kind=='ordinal':assert 'position on this rating scale' in doc.select_one('[title]')['title']


@pytest.mark.skipif(not shutil.which('node'),reason='Node is needed for the grid browser contract')
def test_grid_browser_modes_reuse_images_and_bound_live_leases():
    harness=r'''
const assert=require('node:assert/strict');let pagehide,requests=[],timers=[],decodeResolve,decodeReject;
global.addEventListener=(name,fn)=>{if(name==='pagehide')pagehide=fn;};
global.setTimeout=(fn,ms)=>{timers.push({fn,ms});return timers.length;};global.clearTimeout=()=>{};
const elements={empty:{hidden:true},caption:{textContent:''},lights:{innerHTML:'old'},status:{textContent:''},monitor:{textContent:'Paused'}};
let image={alt:'Test image',hidden:false,naturalWidth:10,removeAttribute(){},replaceWith(next){image=next;}};
const classes=new Set();
const card={dataset:{mode:'captured',operator:'true',answerUrl:'/answers',imageUrl:'/preview',leaseUrl:'/lease',csrf:'offline',zone:'UTC',frame:'A'},
 classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),toggle:(x,on)=>on?classes.add(x):classes.delete(x)},
 querySelector:s=>s==='img'?image:s==='[data-grid-empty]'?elements.empty:s==='[data-grid-caption]'?elements.caption:s==='[data-grid-lights]'?elements.lights:s==='[data-grid-answer-status]'?elements.status:elements.monitor};
global.document={hidden:false,querySelectorAll:()=>[card]};global.window=global;
global.Image=class{constructor(){this.hidden=false;this.naturalWidth=10;}decode(){return new Promise((yes,no)=>{decodeResolve=yes;decodeReject=no;});}replaceWith(next){image=next;}removeAttribute(){}};
function response(status=200,frame='B',monitor=true){return {status,ok:status>=200&&status<300,redirected:false,text:async()=>'<lights B>',headers:{get:k=>({
 'X-VOP-Processed-frame':frame,'X-VOP-Processed-url':frame?'/processed/'+frame:'','X-VOP-Processed-captured':'2026-10-31T09:00:00Z','X-VOP-Processed-message':'Last observation',
 'X-VOP-Monitoring':String(monitor),'ETag':'tag','X-VOP-Frame-Id':frame,'X-VOP-Captured-At':'2026-10-31T09:00:00Z','X-VOP-Preview-Kind':'live','X-VOP-Preview-State':'live'})[k]??null}};}
let answer=response(),head=response();
global.fetch=async(url,options)=>{requests.push({url,options});return url==='/answers'?answer:url==='/preview'?head:{ok:true};};
const flush=()=>new Promise(setImmediate);
(async()=>{
new Function(SOURCE)();await flush();
assert.equal(requests.length,1);assert.equal(image.naturalWidth,10);assert.equal(elements.lights.innerHTML,'old');
decodeResolve();await flush();assert.equal(image.src,'/processed/B');assert.equal(elements.lights.innerHTML,'<lights B>');assert.equal(card.dataset.frame,'B');
assert.ok(classes.has('monitoring'));assert.equal(elements.monitor.textContent,'Monitoring');
// Captured mode never requests live pixels or starts/renews a decoder.
assert.ok(requests.every(r=>r.url==='/answers'));
const answerTimer=timers.find(t=>t.ms===1000);answer=response(304);const existing=image;await answerTimer.fn();assert.equal(image,existing);
answer=response(200,'');await timers.filter(t=>t.ms===1000).at(-1).fn();assert.equal(image.hidden,true);
answer={ok:false,status:500};await timers.filter(t=>t.ms===1000).at(-1).fn();assert.ok(classes.has('answers-offline'));
// Hidden tabs send nothing; live mode renews a CSRF-protected lease only while monitoring.
document.hidden=true;const before=requests.length;await timers.filter(t=>t.ms===1000).at(-1).fn();assert.equal(requests.length,before);document.hidden=false;
card.dataset.mode='live';answer=response(304);timers=[];new Function(SOURCE)();await flush();
assert.ok(requests.some(r=>r.url==='/lease'&&r.options.method==='POST'&&r.options.body.get('csrf')==='offline'));
decodeResolve();await flush();assert.ok(image.src.startsWith('/preview?frame='));
card.dataset.renewAt='0';head=response(200,'C',false);timers=[];new Function(SOURCE)();await flush();decodeResolve();await flush();
assert.equal(elements.monitor.textContent,'Paused');assert.ok(!classes.has('monitoring'));
assert.equal(requests.filter(r=>r.url==='/lease').length,1);
pagehide();const count=requests.length;for(const t of timers.filter(t=>t.ms===200||t.ms===1000))await t.fn();assert.equal(requests.length,count);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('SOURCE',json.dumps(SCRIPT))
    result=subprocess.run([shutil.which('node')],input=harness,text=True,capture_output=True,timeout=15)
    assert result.returncode==0,result.stderr
