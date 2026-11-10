"""Offline guidance/reconnection only; no real action delivery."""
from dataclasses import replace
from datetime import timedelta

from bs4 import BeautifulSoup
from starlette.testclient import TestClient
from test_phase3_release import app, HEADERS, SID, QID
from test_actions import sound, automation, summary
from vop.contracts import utcnow


def test_blocked_version_is_visible_and_can_be_reviewed_and_reconnected(app,monkeypatch):
    actions,store=app.state.actions,app.state.store
    sound(actions)
    automation(actions,trigger='value',value=True)
    store.update_source(SID,enabled=True,retain_evidence=False,sample_interval_seconds=10)
    old=next(r for r in store.questions(SID) if r['spec'].question_id==QID)
    new=store.edit_question(SID,replace(old['spec'],text='The updated question?'),old['policy'])
    client=TestClient(app,headers=HEADERS)
    listing=client.get('/automations')
    assert 'Needs attention' in listing.text and 'Review and reconnect' in listing.text
    assert 'cannot trigger' in listing.text
    editor=BeautifulSoup(client.get('/automations/edit?id=front-door').text,'html.parser')
    assert old['spec'].text in editor.text and new.text in editor.text
    assert 'Previously, version 1' in editor.text and 'Now, version 2' in editor.text
    assert 'Save and reconnect' in editor.text
    assert editor.select_one('[name=expected_question_version]')['value']=='2'
    assert actions.automations()[0]['question_version']=='1' and not actions.jobs()
    assert 'Automations need attention' in client.get('/').text
    assert 'Automations need attention' in client.get('/activity').text
    data=client.get('/api/v1/diagnostics').json()
    assert data['automation_attention'][0]['name']=='Visitor at door'
    form={'id':'front-door','condition':SID+'/'+QID,'name':'Visitor at door','trigger':'value','value':'true','actions':'bell',
          'cooldown':'00:01:00','max_hour':'10','enabled':'yes','expected_question_version':new.version}
    stale={**form,'expected_question_version':'1'}
    assert client.post('/automations/save',data=stale).status_code==400
    assert actions.automations()[0]['question_version']=='1'
    assert client.post('/automations/save',data=form).status_code==200
    assert actions.automations()[0]['question_version']==new.version
    assert not actions.automation_attention() and not actions.jobs()
    # The existing Yes becomes a baseline, not a replayed alert.
    now=utcnow()+timedelta(seconds=1)
    current=summary(now,state='ACTIVE',value=True)
    monkeypatch.setattr(actions,'summary',lambda *a,**kw:current)
    actions.evaluate(now)
    assert not actions.jobs()
