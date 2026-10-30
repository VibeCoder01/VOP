"""Exact completed answer frames, using synthetic pixels and no cameras/models."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from threading import Event
import shutil
import subprocess
import pytest
from bs4 import BeautifulSoup
from PIL import Image
from starlette.testclient import TestClient

from test_removed_question_bulk import app, no_workers, login, SID, VIEWER, OWNER
from vop.inputs.sources import capture_inline
from vop.dashboard import OBSERVE_ANSWERS_JS


def colored_frame(pipeline, color):
    buffer = BytesIO()
    Image.new('RGB',(40,20),color).save(buffer,format='PNG')
    payload = buffer.getvalue()
    return replace(capture_inline(pipeline.sources[SID]),payload=payload,width=40,height=20,sha256=sha256(payload).hexdigest())


def test_processed_pair_keeps_completed_frame_until_new_answers_commit(app, monkeypatch):
    store,pipeline = app.state.store,app.state.pipeline
    pipeline.sources[SID] = replace(pipeline.sources[SID],settings={'privacy_masks':[[0,0,.5,1]]})
    store.update_source(SID,enabled=True,retain_evidence=False,sample_interval_seconds=10)
    first = colored_frame(pipeline,'red')
    pipeline.run(SID,first)
    entered,release = Event(),Event()
    original = pipeline.engine.infer
    def delayed(request):
        entered.set()
        assert release.wait(30),'Test must release synthetic inference'
        return original(request)
    monkeypatch.setattr(pipeline.engine,'infer',delayed)
    second = colored_frame(pipeline,'blue')
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/ui/mode',data={'csrf':csrf,'mode':'view'})
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(pipeline.run,SID,second)
            try:
                assert entered.wait(10)
                assert pipeline.previews[SID][0] == second.frame_id
                assert pipeline.processed_previews[SID][0] == first.frame_id
                response = client.get('/ui/camera-answers/' + SID)
                assert response.headers['x-vop-processed-frame'] == first.frame_id
                url = response.headers['x-vop-processed-url']
                image = Image.open(BytesIO(client.get(url).content)).convert('RGB')
                assert image.getpixel((0,0)) == (0,0,0)
                assert image.getpixel((39,0)) == (255,0,0)
                soup = BeautifulSoup(client.get('/').text,'html.parser')
                pair = soup.select_one('.image-pair')
                assert len(pair.select('.image-stage img')) == 2
                assert pair.select_one('[data-processed-image] img')['src'] == url
                assert client.head('/ui/live-preview/' + SID).headers['x-vop-frame-id'] == second.frame_id
            finally:
                release.set()
            # This verifies frame identity across a commit, not disk latency.
            # Leave room for SQLite/Windows runner contention after releasing it.
            pending.result(timeout=30)
        updated = client.get('/ui/camera-answers/' + SID)
        assert updated.headers['x-vop-processed-frame'] == second.frame_id
        assert client.get('/ui/processed-image/' + SID + '/' + first.frame_id).status_code == 404
        image = Image.open(BytesIO(client.get(updated.headers['x-vop-processed-url']).content)).convert('RGB')
        assert image.getpixel((39,0)) == (0,0,255)
        for method in (client.get,client.head):
            assert method(updated.headers['x-vop-processed-url'],headers={'Authorization':'Bearer '+VIEWER}).status_code == 403


def test_no_unrelated_fallback_after_clear_or_image_deletion(app):
    store,pipeline = app.state.store,app.state.pipeline
    with TestClient(app) as client:
        login(client)
        first,second = colored_frame(pipeline,'red'),colored_frame(pipeline,'blue')
        store.update_source(SID,enabled=True,retain_evidence=True,sample_interval_seconds=0)
        pipeline.run(SID,first)
        store.update_source(SID,enabled=True,retain_evidence=False,sample_interval_seconds=0)
        pipeline.run(SID,second)
        pipeline.latest_preview = None  # Simulate transient preview loss/restart.
        missing = client.get('/ui/camera-answers/' + SID)
        assert missing.headers['x-vop-processed-url'] == ''
        assert 'not saved' in missing.headers['x-vop-processed-message']
        assert store.evidence(SID,first.frame_id) is not None  # Older saved bytes must not be substituted.
        store.update_source(SID,enabled=True,retain_evidence=True,sample_interval_seconds=0)
        third = colored_frame(pipeline,'green')
        pipeline.run(SID,third)
        pipeline.latest_preview = None
        saved = client.get('/ui/camera-answers/' + SID)
        assert saved.headers['x-vop-processed-frame'] == third.frame_id
        assert client.get(saved.headers['x-vop-processed-url']).status_code == 200
        assert client.post('/ui/evidence/' + SID + '/' + third.frame_id + '/delete',headers={'Authorization':'Bearer '+OWNER}).status_code == 200
        removed = client.get('/ui/camera-answers/' + SID,headers={'If-None-Match':saved.headers['etag']})
        assert removed.status_code == 200 and removed.headers['x-vop-processed-url'] == ''


def test_non_inference_preview_does_not_replace_answer_frame(app):
    pipeline = app.state.pipeline
    with TestClient(app) as client:
        login(client)
        frame = colored_frame(pipeline,'red')
        pipeline.run(SID,frame)
        other = colored_frame(pipeline,'blue')
        pipeline.remember_preview(SID,other.frame_id,other.payload,other.captured_at_utc)
        assert client.get('/ui/camera-answers/' + SID).headers['x-vop-processed-frame'] == frame.frame_id


def test_capture_committing_during_answer_render_cannot_mismatch_frame(app, monkeypatch):
    pipeline,store = app.state.pipeline,app.state.store
    with TestClient(app) as client:
        login(client)
        pipeline.run(SID,colored_frame(pipeline,'red'))
        second = colored_frame(pipeline,'blue')
        original = store.summary
        captured = False
        def racing(*args,**kwargs):
            nonlocal captured
            if not captured:
                captured = True
                pipeline.engine.configure_source_answer(SID,'red_square','1',False)
                pipeline.run(SID,second)
            return original(*args,**kwargs)
        monkeypatch.setattr(store,'summary',racing)
        response = client.get('/ui/camera-answers/' + SID)
        assert response.headers['x-vop-processed-frame'] == second.frame_id
        assert response.headers.get('etag') is None
        rows = BeautifulSoup(response.text,'html.parser').select('tbody tr')
        assert rows[0].select('td')[2].text == 'No'
        next_response = client.get('/ui/camera-answers/' + SID)
        assert next_response.headers['etag']


def test_clear_after_commit_cannot_republish_deleted_preview(app, monkeypatch):
    pipeline,store = app.state.pipeline,app.state.store
    store.update_source(SID,enabled=True,retain_evidence=True,sample_interval_seconds=0)
    original = store.save
    def cleared(source_id,frame,*args,**kwargs):
        saved = original(source_id,frame,*args,**kwargs)
        store.delete_evidence(source_id,frame.frame_id)
        pipeline.clear_preview(source_id,frame.frame_id)
        return saved
    monkeypatch.setattr(store,'save',cleared)
    frame = colored_frame(pipeline,'red')
    pipeline.run(SID,frame)
    assert SID not in pipeline.previews and SID not in pipeline.processed_previews
    assert store.evidence(SID,frame.frame_id) is None


def test_answer_html_and_processed_pixels_swap_together_and_retry_without_reload():
    node = shutil.which('node')
    if not node: pytest.skip('Node is required for the browser-script unit check')
    harness = r"""
const assert=require('node:assert/strict');
let finish,fail,writes=0,timeout;
global.setTimeout=(callback,delay)=>{assert.equal(delay,5000);timeout=callback;return 1;};
global.clearTimeout=()=>{};
global.Image=class {
  constructor(){this.hidden=false;this.naturalWidth=40;this.alt='Processed source frame';}
  set src(value){this.url=value;writes++;}
  removeAttribute(){this.url='';}
  replaceWith(replacement){image=replacement;}
  decode(){return new Promise((resolve,reject)=>{finish=resolve;fail=reject;});}
};
let image=new Image();image.hidden=true;
const empty={},caption={},disclosure={open:true},content={innerHTML:'old answers'};
const tile={dataset:{frame:''},closest:()=>disclosure,
  querySelector:q=>q==='img'?image:q==='[data-processed-empty]'?empty:caption};
const panel={open:true,dataset:{processedTarget:'processed-fixture',zone:'UTC',answerUrl:'/answers?zone=UTC'},querySelector:()=>content,querySelectorAll:()=>[]};
global.document={hidden:false,querySelectorAll:()=>[],getElementById:()=>tile};
const response=(frame,status=200)=>({status,text:async()=>`answers ${frame}`,headers:{get(key){
  return {'X-VOP-Processed-frame':frame,'X-VOP-Processed-url':frame?'/image/'+frame:'',
          'X-VOP-Processed-captured':'2026-10-27T10:00:00+00:00',
          'X-VOP-Processed-message':frame?'Privacy-masked answer frame.':'Image not saved.',ETag:frame}[key]??null;
}}});
let next=response('A');global.fetch=async()=>next;
"""
    checks = r"""
(async()=>{
  const first=refreshAnswers(panel);await new Promise(setImmediate);
  assert.equal(content.innerHTML,'old answers');assert.equal(image.hidden,true);
  finish();await first;
  assert.equal(content.innerHTML,'answers A');assert.equal(tile.dataset.frame,'A');assert.equal(image.url,'/image/A');
  const shown=image;next=response('B');
  const second=refreshAnswers(panel);await new Promise(setImmediate);
  assert.equal(image,shown);assert.equal(content.innerHTML,'answers A');
  finish();await second;
  assert.equal(tile.dataset.frame,'B');assert.equal(content.innerHTML,'answers B');
  disclosure.open=false;next=response('C');const before=writes;await refreshAnswers(panel);
  assert.equal(writes,before);assert.equal(image.hidden,true);assert.equal(content.innerHTML,'answers C');
  disclosure.open=true;next=response('',304);
  const reopened=refreshAnswers(panel);await new Promise(setImmediate);finish();await reopened;
  assert.equal(tile.dataset.frame,'C');assert.equal(image.url,'/image/C');
  next=response('D');const pending=refreshAnswers(panel);await new Promise(setImmediate);
  disclosure.open=false;finish();await pending;
  assert.equal(image.hidden,true);assert.equal(content.innerHTML,'answers D');
  disclosure.open=true;next=response('E');const failed=refreshAnswers(panel);await new Promise(setImmediate);
  fail(new Error('temporary image loss'));await failed;
  assert.equal(image.hidden,true);assert.match(empty.textContent,/Retrying/);assert.equal(content.innerHTML,'answers E');
  next=response('',304);const retry=refreshAnswers(panel);await new Promise(setImmediate);finish();await retry;
  assert.equal(tile.dataset.frame,'E');assert.equal(image.hidden,false);
  next=response('');await refreshAnswers(panel);
  assert.equal(image.hidden,true);assert.equal(tile.dataset.frame,'');assert.equal(empty.textContent,'Image not saved.');
  next=response('F');const stalled=refreshAnswers(panel);await new Promise(setImmediate);timeout();await stalled;
  assert.equal(image.hidden,true);assert.equal(content.innerHTML,'answers F');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    result=subprocess.run([node],input='\n'.join((harness,OBSERVE_ANSWERS_JS,checks)),capture_output=True,text=True)
    assert result.returncode == 0,result.stderr
