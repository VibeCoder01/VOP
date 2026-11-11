"""Offline hover overlays: no images or cameras are fetched."""
import json
import shutil
import subprocess

import pytest
from bs4 import BeautifulSoup
from starlette.testclient import TestClient
from test_phase3_release import app, HEADERS, SID, QID, TOKEN
from test_phase2_browser_storage import login
from vop.measurements import QueryPolicy
from vop.question_area_preview import SCRIPT


def test_configured_areas_are_on_focusable_question_rows_and_refresh(app):
    areas = {'include_regions':[[.1,.2,.3,.4]],'exclude_regions':[[.2,.3,.1,.1]]}
    spec = app.state.store.questions(SID)[0]['spec']
    app.state.store.edit_question(SID, spec, QueryPolicy(**areas))
    client = TestClient(app)
    csrf = login(client, TOKEN)
    client.post('/ui/mode', data={'csrf':csrf,'mode':'view'})
    soup = BeautifulSoup(client.get('/').text,'html.parser')
    assert soup.select_one('script[src="/ui/question-area-preview.js"]')
    row = soup.select_one('[data-question-areas]')
    assert row['tabindex']=='0'
    assert json.loads(row['data-question-areas']) == {'include':areas['include_regions'],'exclude':areas['exclude_regions']}
    assert 'Hover or focus' in row['title']
    fragment = BeautifulSoup(client.get('/ui/camera-answers/'+SID).text,'html.parser')
    assert json.loads(fragment.select_one('[data-question-areas]')['data-question-areas']) == json.loads(row['data-question-areas'])
    script = client.get('/ui/question-area-preview.js')
    assert script.status_code==200 and 'createElementNS' in script.text
    app.state.store.edit_question(SID, spec, QueryPolicy())
    assert 'data-question-areas' not in client.get('/ui/camera-answers/'+SID).text


def test_letterbox_geometry_camera_targeting_and_cleanup():
    node=shutil.which('node')
    if not node: pytest.skip('Node required for overlay check')
    harness=r"""
const assert=require('node:assert/strict');
const listeners={}, windowListeners={};
const nodes=[];
function element(){return {attrs:{}, children:[],setAttribute(k,v){this.attrs[k]=v},append(x){this.children.push(x)},remove(){this.removed=true}}}
const box=element();box.clientWidth=400;box.clientHeight=200;
const img={hidden:false,naturalWidth:400,naturalHeight:400};
const tile=element();tile.querySelector=s=>s==='img'?img:box;
const panel={open:true,dataset:{processedTarget:'camera-B'}};
const row={dataset:{questionAreas:JSON.stringify({include:[[.1,.2,.3,.4]],exclude:[[.2,.3,.1,.1]]}),questionLabel:'Example'},closest:()=>panel,contains:x=>x===row,isConnected:true};
const target={closest:()=>row};
global.document={hidden:false,addEventListener(k,f){listeners[k]=f},getElementById(id){assert.equal(id,'camera-B');return tile},createElementNS(ns,name){const e=element();nodes.push(e);return e},createElement(){return element()},querySelectorAll(){return []}};
global.window={addEventListener(k,f){windowListeners[k]=f}};
"""
    checks=r"""
listeners.mouseover({target});
const svg=box.children[0];assert.equal(svg.attrs.viewBox,'0 0 400 200');
assert.deepEqual(svg.children[0].attrs,{x:'120',y:'40',width:'60',height:'80',class:'include'});
assert.equal(svg.children[1].attrs.class,'exclude');
assert.ok(tile.children[0].textContent.includes('takes priority'));
listeners.mouseout({target,relatedTarget:null});assert.ok(svg.removed);
listeners.focusin({target});assert.equal(box.children.length,2);
listeners.focusout({relatedTarget:null});assert.ok(box.children[1].removed);
img.hidden=true;listeners.mouseover({target});assert.equal(box.children.length,2);
img.hidden=false;listeners.mouseover({target});document.hidden=true;listeners.visibilitychange();assert.ok(box.children[2].removed);
document.hidden=false;tile.dataset={crop:'[0.5,0,0.5,1]'};
row.dataset.questionAreas=JSON.stringify({include:[[.6,.2,.2,.4]],exclude:[]});
listeners.mouseover({target});const cropped=box.children.at(-1).children[0];
assert.equal(cropped.attrs.x,'140');assert.equal(cropped.attrs.width,'80');
assert.ok(!/fetch\(/.test(SCRIPT_TEXT));
console.log('PASS');
"""
    result=subprocess.run([node,'-e',harness+'\nconst SCRIPT_TEXT='+json.dumps(SCRIPT)+';\n'+SCRIPT+'\n'+checks],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert 'PASS' in result.stdout
