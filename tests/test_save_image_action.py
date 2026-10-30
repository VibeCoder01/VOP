"""All images and observations here are synthetic; no camera or email is contacted."""
from dataclasses import replace
from datetime import timedelta
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image
import pytest
from starlette.testclient import TestClient

from test_phase3_release import app, HEADERS, SID, QID
from test_actions import summary, event
from vop.actions import Actions
from vop.contracts import utcnow
from vop.inputs.sources import capture_inline


def capture(app):
    pipeline=app.state.pipeline
    frame=capture_inline(pipeline.sources[SID])
    pipeline.run(SID,frame)
    with app.state.store.connection() as db:
        oid=db.execute('SELECT id FROM observations WHERE source_id=? AND question_id=? ORDER BY sequence DESC LIMIT 1',(SID,QID)).fetchone()[0]
    return frame,{'source_id':SID,'observation_id':oid}


def image_action(app,aid='save-picture'):
    actions=app.state.actions
    actions.save_action({'id':aid,'kind':'image','name':'Keep the observation image'})
    return next(a for a in actions.definitions() if a['id']==aid)


def test_manual_save_uses_normal_masked_evidence_without_changing_capture_settings(app):
    actions,store,pipeline=app.state.actions,app.state.store,app.state.pipeline
    source=pipeline.sources[SID]
    pipeline.sources[SID]=replace(source,settings={**source.settings,'privacy_masks':[[0,0,.5,1]]})
    before=store.source_control(SID)
    assert not before['retain_evidence']
    frame,context=capture(app)
    expected=pipeline.processed_previews[SID][1]
    assert store.evidence(SID,frame.frame_id) is None
    image_action(app)
    actions.test('save-picture',SID)
    assert actions.jobs()[0]['status']=='completed'
    assert store.evidence(SID,frame.frame_id)==expected
    assert store.observation(context['observation_id'])['image_saved']
    image=Image.open(BytesIO(expected))
    assert image.getpixel((0,0))==(0,0,0)
    assert store.source_control(SID)==before
    # Normal image deletion remains final: there is no queued copy to restore it.
    store.delete_evidence(SID,frame.frame_id)
    actions.deliver()
    assert store.evidence(SID,frame.frame_id) is None
    assert Actions(store,pipeline).jobs()[0]['status']=='completed'


def test_automatic_image_action_deduplicates_and_obeys_suppression(app,monkeypatch):
    actions,store=app.state.actions,app.state.store
    image_action(app)
    actions.save_automation({'id':'front-door','name':'Visitor','source_id':SID,'question_id':QID,
                             'trigger':'start','actions':['save-picture'],'enabled':True,'cooldown':60})
    now=utcnow()+timedelta(seconds=1)
    current=summary(now)
    monkeypatch.setattr(actions,'summary',lambda *a:current)
    actions.evaluate(now)
    frame,context=capture(app)
    # Exercise the real-observation branch using an explicitly synthetic test fixture.
    original=store.observation
    monkeypatch.setattr(store,'observation',lambda oid:{**original(oid),'run':{'synthetic':False}})
    current.update(state='ACTIVE',latest_value=True,last_observation_id=context['observation_id'],events=[event(now+timedelta(seconds=1))])
    actions.evaluate(now+timedelta(seconds=2));actions.evaluate(now+timedelta(seconds=3))
    assert len(actions.jobs())==1 and actions.jobs()[0]['status']=='completed'
    assert store.evidence(SID,frame.frame_id)
    later,_=capture(app)
    current['events'].append(event(now+timedelta(seconds=4),'second-event'))
    actions.evaluate(now+timedelta(seconds=5))
    assert actions.jobs()[0]['status']=='suppressed'
    assert store.evidence(SID,later.frame_id) is None


def test_no_newer_frame_substitution_and_no_missing_capture_fabrication(app):
    config=image_action(app)
    old,context=capture(app)
    capture(app);new,_=capture(app)
    assert app.state.actions.send(config,context,'old')[0]=='blocked'
    assert app.state.store.evidence(SID,old.frame_id) is None
    assert app.state.store.evidence(SID,new.frame_id) is None
    assert app.state.actions.send(config,{'source_id':SID},'missing')[0]=='blocked'


def test_image_and_activity_are_atomic_and_existing_image_is_reused(app):
    actions,store=app.state.actions,app.state.store
    config=image_action(app)
    frame,context=capture(app)
    with pytest.raises(RuntimeError):
        with store.connection() as db:
            actions.enqueue(db,'rollback',None,config,context,utcnow())
            raise RuntimeError('rollback transaction')
    assert not actions.jobs() and store.evidence(SID,frame.frame_id) is None
    with store.connection() as db:
        actions.enqueue(db,'keep',None,config,context,utcnow())
    expected=store.evidence(SID,frame.frame_id)
    app.state.pipeline.clear_preview(SID)
    assert actions.send(config,context,'again')[0]=='completed'
    assert store.evidence(SID,frame.frame_id)==expected
    from vop.history_deletion import question_selection,delete_question_data
    with store.connection() as db:delete_question_data(db,question_selection(db,SID,QID))
    assert store.evidence(SID,frame.frame_id) is None


def test_image_action_forms_require_a_camera_and_take_no_capture(app,monkeypatch):
    monkeypatch.setattr(app.state.pipeline.capture_adapter,'capture',lambda *a:pytest.fail('No capture'))
    with TestClient(app,headers=HEADERS) as client:
        editor=client.get('/actions/edit?kind=image')
        assert editor.status_code==200 and 'privacy-masked' in editor.text
        assert client.post('/actions/save',data={'kind':'image','id':'save-picture','name':'Keep image'}).status_code==200
        doc=BeautifulSoup(client.get('/actions').text,'html.parser')
        assert doc.select_one('form[action="/actions/save-picture/test"] select[name="source_id"][required]')
        assert client.post('/actions/save-picture/test').status_code==400
        assert client.post('/actions/save-picture/test',data={'source_id':SID}).status_code==200
        assert app.state.actions.jobs()[0]['status']=='blocked'
        assert 'text only' in client.get('/actions/edit?kind=email').text
