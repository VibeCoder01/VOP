"""Synthetic images only: masks are applied before every inference transport."""
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
import json

from bs4 import BeautifulSoup
from PIL import Image
import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER
from vop.inference.mock import MockInferenceEngine
from vop.inputs.sources import capture_inline
from vop.measurements import QueryPolicy
from vop.preprocessing import preprocess
from vop.service import create_app

SID = 'synthetic-scene'


def white_frame(source):
    image=Image.new('RGB',(100,100),'white')
    buffer=BytesIO();image.save(buffer,format='PNG');data=buffer.getvalue()
    return replace(capture_inline(replace(source,kind='synthetic',settings={})),payload=data,width=100,height=100,sha256=sha256(data).hexdigest())


@pytest.mark.parametrize('field', ['include_regions','exclude_regions'])
@pytest.mark.parametrize('value', [None,{},[None],[[0,0,0,1]],[[.9,0,.2,1]],[[True,0,.5,1]],[[0,0,float('nan'),1]],[[0,0,.1,.1]]*17])
def test_question_regions_reject_invalid_shapes(field,value):
    with pytest.raises(ValueError): QueryPolicy(**{field:value})


def test_include_union_exclude_and_camera_privacy_order(app):
    frame=white_frame(app.state.pipeline.sources[SID])
    result=preprocess(frame, [[0,0,.2,1]], include_regions=((0,0,.8,1),),exclude_regions=((.5,0,.1,1),))
    with Image.open(BytesIO(result.payload)) as image:
        assert image.getpixel((10,50))==(0,0,0)  # A question cannot undo camera privacy.
        assert image.getpixel((30,50))==(255,255,255)
        assert image.getpixel((55,50))==(0,0,0)
        assert image.getpixel((90,50))==(0,0,0)
    assert Image.open(BytesIO(frame.payload)).getpixel((10,50))==(255,255,255)
    union=preprocess(frame,include_regions=((0,0,.2,1),(.8,0,.2,1)))
    image=Image.open(BytesIO(union.payload))
    assert image.getpixel((10,50))==image.getpixel((90,50))==(255,255,255)
    assert image.getpixel((50,50))==(0,0,0)
    assert QueryPolicy(include_regions=[[0,0,.5,1]]).include_regions==((0.,0.,.5,1.),)
    assert QueryPolicy().include_regions==QueryPolicy().exclude_regions==()


def test_question_list_marks_only_question_areas_and_removes_marker_when_cleared(app):
    store = app.state.store
    records = store.questions(SID)
    store.edit_question(SID,records[0]['spec'],QueryPolicy(include_regions=((0,0,.5,1),)))
    store.edit_question(SID,records[1]['spec'],QueryPolicy(exclude_regions=((0,0,.5,1),)))
    store.edit_question(SID,records[2]['spec'],QueryPolicy(roi=(0,0,.5,1)))
    with TestClient(app) as client:
        login(client)
        doc=BeautifulSoup(client.get('/?view=questions').text,'html.parser')
        markers=doc.select('.question-area-marker')
        assert len(markers)==3
        assert ['Include','Exclude','Region of interest']==[m['title'].split(': ')[1].split('.')[0] for m in markers]
        for record in store.questions(SID):
            store.edit_question(SID,record['spec'],QueryPolicy())
        assert not BeautifulSoup(client.get('/?view=questions').text,'html.parser').select('.question-area-marker')


def test_pipeline_groups_by_full_question_mask_and_preserves_provenance(app):
    pipeline,store=app.state.pipeline,app.state.store
    seen={}
    class Inspect(MockInferenceEngine):
        def infer(self,request):
            image=Image.open(BytesIO(request.frame.payload))
            for question in request.questions:
                seen[question.question_id]=(image.getpixel((25,50)),image.getpixel((75,50)))
            return super().infer(request)
    pipeline.engine=Inspect(pipeline.settings.mock_answers,pipeline.settings.engine_id)
    records=store.questions(SID)
    store.edit_question(SID,records[0]['spec'],QueryPolicy(include_regions=((0,0,.5,1),)))
    store.edit_question(SID,records[1]['spec'],QueryPolicy(exclude_regions=((0,0,.5,1),)))
    saved=pipeline.run(SID,white_frame(pipeline.sources[SID]))
    assert seen[records[0]['spec'].question_id]==((255,255,255),(0,0,0))
    assert seen[records[1]['spec'].question_id]==((0,0,0),(255,255,255))
    assert seen[records[2]['spec'].question_id]==((255,255,255),(255,255,255))
    assert len(saved['result']['preprocessing']['question_masks'])==2
    assert len(saved['result']['answers'])==3
    from vop.history_deletion import question_selection, delete_question_data
    qid=records[0]['spec'].question_id
    with store.connection() as db:
        delete_question_data(db,question_selection(db,SID,qid))
        body=json.loads(db.execute('SELECT result_json FROM runs WHERE id=?',(saved['run_id'],)).fetchone()[0])
        assert qid not in body['preprocessing']['question_masks']
        assert len(body['preprocessing']['question_masks'])==1


def test_question_form_persists_regions_in_new_version_without_capture(app,monkeypatch):
    monkeypatch.setattr(app.state.pipeline.capture_adapter,'capture',lambda *_:pytest.fail('Opening or saving a form must not capture'))
    with TestClient(app) as client:
        csrf=login(client)
        page=BeautifulSoup(client.get('/ui/questions/'+SID+'/red_square').text,'html.parser')
        assert page.select_one('[data-mask-editor]') and page.select_one('script[src="/ui/mask-editor.js"]')
        data={'csrf':csrf,'question_id':'red_square','text':'A region question','kind':'binary','expected_version':'1',
              'max_gap_seconds':'00:01:00','enabled':'on','include_regions':'[[0,0,0.5,1]]','exclude_regions':'[[0.2,0.2,0.1,0.1]]'}
        assert client.post('/ui/questions/'+SID+'/red_square',data=data,follow_redirects=False).status_code==303
        record=next(r for r in app.state.store.questions(SID) if r['spec'].question_id=='red_square')
        assert record['spec'].version=='2' and record['policy'].include_regions==((0.,0.,.5,1.),)
        data.update(expected_version='2');data.pop('include_regions');data.pop('exclude_regions')
        assert client.post('/ui/questions/'+SID+'/red_square',data=data,follow_redirects=False).status_code==303
    restored=create_app(app.state.pipeline.settings,token=OWNER)
    record=next(r for r in restored.state.store.questions(SID) if r['spec'].question_id=='red_square')
    assert record['policy'].exclude_regions==((.2,.2,.1,.1),)


def test_mask_grab_queues_without_model_saving_or_camera_privacy_bypass(app,monkeypatch):
    pipeline=app.state.pipeline
    pipeline.sources[SID]=replace(pipeline.sources[SID],settings={'privacy_masks':[[0,0,.5,1]]})
    calls=[]
    def capture(source):calls.append(source.source_id);return white_frame(source)
    monkeypatch.setattr(app.state.sampler,'start',lambda:None)
    monkeypatch.setattr(pipeline.capture_adapter,'capture',capture)
    monkeypatch.setattr(pipeline.engine,'infer',lambda *_:pytest.fail('Image grabs must not run inference'))
    root='/ui/question-mask/'+SID
    with TestClient(app) as client:
        assert client.get(root+'/image').status_code==401
        csrf=login(client)
        assert client.get('/ui/questions/'+SID+'/red_square').status_code==200 and not calls
        assert client.post(root+'/grab',data={}).status_code==403
        assert client.post(root+'/grab',headers={'Authorization':'Bearer '+VIEWER}).status_code==403
        pipeline.busy.acquire()
        try:
            assert client.post(root+'/grab',data={'csrf':csrf}).status_code==202
            assert client.post(root+'/grab',data={'csrf':csrf}).status_code==202
            assert len(app.state.sampler.camera_tests)==1
            app.state.sampler.tick();assert not calls
        finally:pipeline.busy.release()
        app.state.sampler.tick()
        info=client.get(root+'/image').json()
        assert info['status']=='ready' and calls==[SID]
        response=client.get(root+'/image?token='+info['token'])
        image=Image.open(BytesIO(response.content));assert image.getpixel((10,50))==(0,0,0)
        assert image.getpixel((90,50))==(255,255,255)
        assert app.state.store.health()['observation_count']==0
        assert client.get(root+'/image?token=wrong').status_code==404
        pipeline.clear_preview(SID)
        assert client.get(root+'/image?token='+info['token']).status_code==404
        client.post(root+'/grab',data={'csrf':csrf});pipeline.clear_preview(SID);app.state.sampler.tick()
        assert calls==[SID]  # Deleted/cleared requests cannot republish an editor image.


def test_usb_editor_grab_releases_live_preview_device(app,monkeypatch):
    from types import SimpleNamespace
    pipeline=app.state.pipeline
    pipeline.sources[SID]=replace(pipeline.sources[SID],kind='usb',settings={'device':0})
    closed=[]
    pipeline.live_previews.workers[SID]=SimpleNamespace(close=lambda:closed.append(True))
    monkeypatch.setattr(app.state.sampler,'start',lambda:None)
    monkeypatch.setattr(pipeline.capture_adapter,'capture',white_frame)
    with TestClient(app) as client:
        csrf=login(client)
        assert client.post('/ui/question-mask/'+SID+'/grab',data={'csrf':csrf}).status_code==202
        app.state.sampler.tick()
        assert client.get('/ui/question-mask/'+SID+'/image').json()['status']=='ready'
        assert closed==[True] and SID not in pipeline.live_previews.suspended


def test_expired_pending_grab_is_reaped_without_opening_camera(app,monkeypatch):
    from time import monotonic
    clock=monotonic()
    monkeypatch.setattr('vop.mask_editor.monotonic',lambda:clock)
    monkeypatch.setattr('vop.sampling.monotonic',lambda:clock)
    monkeypatch.setattr(app.state.sampler,'start',lambda:None)
    monkeypatch.setattr(app.state.pipeline.capture_adapter,'capture',lambda *_:pytest.fail('An expired grab must not open a camera'))
    with TestClient(app) as client:
        csrf=login(client)
        assert client.post('/ui/question-mask/'+SID+'/grab',data={'csrf':csrf}).status_code==202
        clock+=301
        app.state.sampler.tick()
        assert SID not in app.state.pipeline.mask_grabs
        assert client.get('/ui/question-mask/'+SID+'/image').json()['status']=='empty'


def test_new_grab_after_expiry_replaces_the_stale_queued_callback(app,monkeypatch):
    from time import monotonic
    clock=monotonic()
    monkeypatch.setattr('vop.mask_editor.monotonic',lambda:clock)
    monkeypatch.setattr('vop.sampling.monotonic',lambda:clock)
    monkeypatch.setattr(app.state.sampler,'start',lambda:None)
    monkeypatch.setattr(app.state.pipeline.capture_adapter,'capture',white_frame)
    root='/ui/question-mask/'+SID
    with TestClient(app) as client:
        csrf=login(client)
        client.post(root+'/grab',data={'csrf':csrf})
        old=client.get(root+'/image').json()['token']
        clock+=301
        client.post(root+'/grab',data={'csrf':csrf})
        assert client.get(root+'/image').json()['token']!=old
        app.state.sampler.tick()
        assert client.get(root+'/image').json()['status']=='ready'
