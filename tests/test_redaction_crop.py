"""Geometry-defined crops, synthetic images and offline engine inspection only."""
from dataclasses import replace
from io import BytesIO

from PIL import Image
import pytest
from bs4 import BeautifulSoup
from starlette.testclient import TestClient
from test_phase4_worker import app, login, VIEWER
from test_question_masks import white_frame, SID
from vop.contracts import ProviderError
from vop.measurements import QueryPolicy
from vop.preprocessing import preprocess, redaction_box


def test_crop_uses_masks_not_dark_pixels_and_keeps_editor_coordinates(app):
    f=white_frame(app.state.pipeline.sources[SID])
    masks=((0,0,.2,1),(.8,0,.2,1),(0,0,1,.2),(0,.8,1,.2))
    assert redaction_box((100,100),masks)==(21,21,80,80)
    out=preprocess(f,masks)
    assert (out.width,out.height)==(59,59)
    assert Image.open(BytesIO(out.payload)).getpixel((0,0))==(255,255,255)
    editor=preprocess(f,masks,crop_redacted=False)
    assert (editor.width,editor.height)==(100,100)
    assert Image.open(BytesIO(editor.payload)).getpixel((0,0))==(0,0,0)
    buffer=BytesIO();Image.new('RGB',(100,100),'black').save(buffer,format='PNG')
    dark=replace(f,payload=buffer.getvalue())
    assert preprocess(dark).width==100  # A naturally dark border is not a configured redaction.
    # Separated include windows keep their intervening black region, no stitching.
    union=preprocess(f,include_regions=((.1,.2,.2,.3),(.7,.2,.2,.3)))
    assert (union.width,union.height)==(80,30)
    assert Image.open(BytesIO(union.payload)).getpixel((35,10))==(0,0,0)


def test_roi_and_exclusion_are_applied_in_original_coordinates(app):
    f=white_frame(app.state.pipeline.sources[SID])
    out=preprocess(f,((0,0,.2,1),),roi=(.1,.1,.6,.6),exclude_regions=((.4,.3,.1,.1),))
    assert (out.width,out.height)==(49,60)
    image=Image.open(BytesIO(out.payload))
    assert image.getpixel((24,25))==(0,0,0)  # Original x45,y35 remains excluded.
    with pytest.raises(ProviderError,match='no_visible_image'):
        preprocess(f,((0,0,1,1),),require_visible=True)


def test_engine_image_link_is_exact_cropped_input_and_cleared_with_evidence(app):
    pipeline,store=app.state.pipeline,app.state.store
    records=store.questions(SID)
    q=records[0]['spec']
    pipeline.sources[SID]=replace(pipeline.sources[SID],settings={'privacy_masks':[[0,0,.2,1]]})
    new=store.edit_question(SID,q,QueryPolicy(include_regions=((.25,.25,.5,.5),)))
    f=white_frame(pipeline.sources[SID])
    saved=pipeline.run(SID,f)
    exact=pipeline.engine_previews[SID]['images'][(q.question_id,new.version)]
    assert (exact.width,exact.height)==(50,50)
    assert saved['result']['preprocessing']['source_crop']==[.21,0,.79,1]
    assert q.question_id in saved['result']['preprocessing']['question_crops']
    client=TestClient(app);login(client)
    fragment=BeautifulSoup(client.get('/ui/camera-answers/'+SID).text,'html.parser')
    link=fragment.find('a',string='Engine image')
    assert link
    response=client.get(link['href'])
    assert response.status_code==200 and response.content==exact.payload
    assert client.get(link['href'],headers={'Authorization':'Bearer '+VIEWER}).status_code==403
    pipeline.clear_preview(SID,f.frame_id)
    assert client.get(link['href']).status_code==404


def test_fully_hidden_question_does_not_reach_engine(app,monkeypatch):
    pipeline,store=app.state.pipeline,app.state.store
    records=store.questions(SID)
    hidden=records[0]['spec']
    store.edit_question(SID,hidden,QueryPolicy(exclude_regions=((0,0,1,1),)))
    original=pipeline.engine.infer;seen=[]
    def inspect(request):
        seen.extend(q.question_id for q in request.questions)
        return original(request)
    monkeypatch.setattr(pipeline.engine,'infer',inspect)
    result=pipeline.run(SID,white_frame(pipeline.sources[SID]))['result']
    answer=next(a for a in result['answers'] if a['question_id']==hidden.question_id)
    assert hidden.question_id not in seen and answer['error']['code']=='no_visible_image'
