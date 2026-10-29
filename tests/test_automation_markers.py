from datetime import timedelta
import json
import shutil
import subprocess

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login
from vop.automation_markers import markers, SCRIPT, CSS
from vop.contracts import utcnow

SID='synthetic-scene'


def setup(app,monkeypatch):
    for worker in (app.state.sampler,app.state.reliable,app.state.actions):monkeypatch.setattr(worker,'start',lambda:None)
    actions=app.state.actions
    actions.save_action({'id':'bell','name':'Bell','kind':'beep','location':'browser','volume':50})
    actions.save_automation({'id':'visitor','name':'Visitor','source_id':SID,'question_id':'red_square','trigger':'start','actions':['bell'],'enabled':True})
    return actions


def trigger(actions,stamp,*,reason='',mid='visitor'):
    with actions.store.connection() as db:
        actions.enqueue(db,'fixture-'+str(stamp.timestamp()),mid,actions.definitions()[0],
                        {'source_id':SID,'question_id':'red_square','question_version':'1'},stamp,reason)


def test_marker_updates_without_a_capture_and_expires_with_etag(app,monkeypatch):
    actions=setup(app,monkeypatch);now=utcnow()
    monkeypatch.setattr('vop.automation_markers.utcnow',lambda:now)
    path='/ui/camera-answers/'+SID
    with TestClient(app) as client:
        login(client)
        first=client.get(path)
        star=BeautifulSoup(first.text,'html.parser').select_one('.automation-marker')
        assert star.text=='*' and 'is-triggered' not in star.get('class',[])
        assert '1 linked automation' in star['title']
        assert client.get(path,headers={'If-None-Match':first.headers['etag']}).status_code==304
        trigger(actions,now)
        triggered=client.get(path,headers={'If-None-Match':first.headers['etag']})
        assert triggered.status_code==200
        star=BeautifulSoup(triggered.text,'html.parser').select_one('.automation-marker.is-triggered')
        assert star and int(star['data-automation-until'])==int((now+timedelta(seconds=8)).timestamp()*1000)
        assert app.state.store.health()['observation_count']==0
        now+=timedelta(seconds=9)
        expired=client.get(path,headers={'If-None-Match':triggered.headers['etag']})
        assert expired.status_code==200 and 'is-triggered' not in expired.text
        actions.delete('automation','visitor')
        assert 'automation-marker' not in client.get(path).text


def test_suppressed_old_and_manual_jobs_do_not_flash(app,monkeypatch):
    actions=setup(app,monkeypatch);now=utcnow()
    monkeypatch.setattr('vop.automation_markers.utcnow',lambda:now)
    trigger(actions,now,reason='Cooldown')
    trigger(actions,now-timedelta(seconds=9))
    trigger(actions,now-timedelta(seconds=1),mid=None)
    assert markers(actions.store,SID,{'red_square':'1'})['red_square']['until']==0


@pytest.mark.skipif(not shutil.which('node'),reason='Node required for marker timeout contract')
def test_marker_timer_is_bounded_not_restarted_and_honours_expiry():
    harness=r"""
const assert=require('node:assert/strict');let timers=[];Date.now=()=>1000;
global.setTimeout=(fn,delay)=>{timers.push({fn,delay});};
const make=until=>({dataset:{automationUntil:String(until)},classList:{remove(name){assert.equal(name,'is-triggered');this.removed=true;}}});
const recent=make(6000),expired=make(500),panel={querySelectorAll:()=>[recent,expired]};
eval(SOURCE);armAutomationMarkers(panel);armAutomationMarkers(panel);
assert.equal(timers.length,1);assert.equal(timers[0].delay,5000);assert(expired.classList.removed);
timers[0].fn();assert(recent.classList.removed);
armAutomationMarkers({querySelectorAll:()=>[make(20000)]});assert.equal(timers[1].delay,8000);
""".replace('SOURCE',json.dumps(SCRIPT))
    result=subprocess.run([shutil.which('node'),'-e',harness],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert 'prefers-reduced-motion:reduce' in CSS
