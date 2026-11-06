"""Offline grouping and browser expansion-state checks."""
import json
import shutil
import subprocess

import pytest
from bs4 import BeautifulSoup
from starlette.testclient import TestClient
from test_phase3_release import app, HEADERS
from vop.actions_ui import SCRIPT
from vop.storage import dumps


def test_group_by_camera_and_question_across_actions_and_versions(app):
    with app.state.store.connection() as db:
        for i, sid, qid, version in [(1,'camera-a','question-a','1'),(2,'camera-a','question-a','2'),(3,'camera-b','question-a','1'),(4,'camera-a','question-b','1'),(5,None,None,None)]:
            stamp=f'2026-11-06T09:00:0{i}+00:00'
            db.execute('INSERT INTO action_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (str(i),None,'action-'+str(i),stamp,stamp,stamp,'completed',1,
                 dumps({'kind':'beep','name':'Action '+str(i)}),dumps({'source_id':sid,'question_id':qid,'question_version':version,'camera':sid or 'Test camera','question':qid or 'Action test','automation':'Example'}),'Done',None))
    client=TestClient(app,headers=HEADERS)
    soup=BeautifulSoup(client.get('/activity').text,'html.parser')
    groups=soup.select('details[data-activity-group]')
    assert len(groups)==4
    assert all(not g.has_attr('open') for g in groups)
    group=next(g for g in groups if json.loads(g['data-activity-group'])==['question','camera-a','question-a'])
    rows=[r for r in group.select('tr') if r.find('td')]
    assert len(rows)==2 and 'Action 2' in rows[0].text and 'Action 1' in rows[1].text
    assert '2 actions' in group.summary.text
    # Latest group first; same question ID on another camera is separate.
    assert json.loads(groups[0]['data-activity-group'])[0]=='manual'
    filtered=BeautifulSoup(client.get('/activity/rows?action=action-1').text,'html.parser')
    assert len(filtered.select('[data-activity-group]'))==1
    assert '1 action' in filtered.summary.text


def test_refresh_keeps_expanded_groups_and_collapses_new_ones():
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    harness=r"""
const assert=require('node:assert/strict');
let callback, groups=[{dataset:{activityGroup:'a'},open:true},{dataset:{activityGroup:'b'},open:false}];
const activity={querySelectorAll(selector){return selector.includes('[open]')?groups.filter(g=>g.open):groups},set innerHTML(html){groups=['a','b','c'].map(key=>({dataset:{activityGroup:key},open:false}))}};
global.document={hidden:false,querySelector(s){return s==='[data-action-activity]'?activity:null}};
global.location={search:'?result=completed'};
global.setInterval=f=>{callback=f};
global.fetch=async url=>{assert.equal(url,'/activity/rows?result=completed');return {ok:true,redirected:false,text:async()=>'<rows>'}};
"""
    checks=r"""
(async()=>{await callback();assert.deepEqual(groups.map(g=>g.open),[true,false,false]);console.log('PASS')})().catch(e=>{console.error(e);process.exitCode=1});
"""
    r=subprocess.run([node,'-e',harness+'\n'+SCRIPT+'\n'+checks],capture_output=True,text=True,timeout=15)
    assert r.returncode==0,r.stderr
    assert 'PASS' in r.stdout
