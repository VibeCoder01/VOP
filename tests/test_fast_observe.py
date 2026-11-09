"""UI navigation must not request historical calculations or image BLOBs."""
from dataclasses import replace
from datetime import timedelta

import pytest
from starlette.testclient import TestClient
from bs4 import BeautifulSoup
from test_phase3_release import app, HEADERS, SID, QID, TOKEN
from test_phase2_browser_storage import login
from vop.contracts import utcnow
from vop.inputs.sources import capture_inline


def test_camera_selection_and_polling_never_load_history_or_other_cameras(app,monkeypatch):
    pipeline,store=app.state.pipeline,app.state.store
    source=pipeline.sources[SID]
    other=replace(source,source_id='other-camera',name='Other camera')
    store.configure(replace(pipeline.settings,sources=(other,)))
    pipeline.sources[other.source_id]=other
    store.update_source(SID,enabled=True,retain_evidence=True,sample_interval_seconds=0)
    pipeline.run(SID,capture_inline(source))
    pipeline.clear_preview(SID)
    def forbidden(*a,**kw):pytest.fail('History must not be touched on Observe')
    monkeypatch.setattr(store,'summary',forbidden)
    monkeypatch.setattr(store,'_history',forbidden)
    monkeypatch.setattr(store,'_rebuild',forbidden)
    monkeypatch.setattr(store,'event_count',forbidden)
    original=store.current_summary
    visited=[]
    def current(sid,*a,**kw):
        assert sid==SID
        visited.append(sid)
        return original(sid,*a,**kw)
    evidence=store.latest_evidence
    def metadata(sid,**kw):
        assert kw.get('metadata_only'), 'Page/HEAD must not read image bytes'
        return evidence(sid,**kw)
    monkeypatch.setattr(store,'latest_evidence',metadata)
    client=TestClient(app)
    csrf=login(client,TOKEN)
    client.post('/ui/mode',data={'csrf':csrf,'mode':'view'})
    monkeypatch.setattr(store,'current_summary',current)
    response=client.get('/?source='+SID)
    assert response.status_code==200
    assert len(BeautifulSoup(response.text,'html.parser').select('.capture-source'))==1
    assert visited
    assert client.get('/ui/camera-answers/'+SID).status_code==200
    assert client.get('/?source='+SID+'&layout=grid').status_code==200
    assert client.head('/ui/live-preview/'+SID).status_code==200


def test_current_state_matches_replay_staleness_and_controls(app):
    pipeline,store=app.state.pipeline,app.state.store
    for value in (False,True,True,False):
        pipeline.engine.configure_source_answer(SID,QID,'1',value)
        pipeline.run(SID,capture_inline(pipeline.sources[SID]))
        now=utcnow()
        current=store.current_summary(SID,QID,'1',as_of=now)
        full=store.summary(SID,QID,'1',as_of=now)
        for key in ('state','latest_value','last_observation_id','last_observed_at_utc','stale'):
            assert current[key]==full[key]
    assert store.current_summary(SID,QID,'1',as_of=now+timedelta(hours=1))['latest_value'] is None
    store.update_source(SID,enabled=False,retain_evidence=False,sample_interval_seconds=0)
    assert store.current_summary(SID,QID,'1')['disabled']


def test_current_snapshot_is_not_published_on_rollback_and_not_mutable_by_reader(app):
    pipeline,store=app.state.pipeline,app.state.store
    pipeline.run(SID,capture_inline(pipeline.sources[SID]))
    before=store.current_summary(SID,QID,'1')
    with pytest.raises(RuntimeError):
        with store.connection() as db:
            db.execute("UPDATE observations SET status='timeout',normalised_state='error',answer_json='{\"value\":null}' WHERE question_id=?",(QID,))
            store._rebuild(db,SID,QID,'1')
            raise RuntimeError('rollback')
    assert store.current_summary(SID,QID,'1')==before
    read=store.current_summary(SID,QID,'1');read['state']='WRONG'
    assert store.current_summary(SID,QID,'1')==before
    # Retention changes a row in place: a cached answer must never resurrect it.
    with store.connection() as db:
        db.execute("UPDATE observations SET status='retention_gap',normalised_state='unknown',answer_json='{\"value\":null}' WHERE question_id=?",(QID,))
    assert store.current_summary(SID,QID,'1')['latest_value'] is None
