"""Episode selection/rendering/zoom checks with disposable synthetic history."""
import shutil
import subprocess
from bs4 import BeautifulSoup
import pytest
from fasthtml.common import to_xml
from starlette.testclient import TestClient
from test_history_camera_buttons import app, no_workers, history, login, SID
from vop.episodes_ui import TITLE, EPISODES_JS, episode_timeline, intervals
from vop.measurements import utc


def test_camera_buttons_show_all_time_counts_and_timeline_follows_selection(app):
    ids = history(app)
    store = app.state.store
    before = {sid:store.source_control(sid) for sid in ids}
    with TestClient(app) as client:
        login(client)
        client.post('/ui/mode', data={'csrf':BeautifulSoup(client.get('/').text,'html.parser').select_one('[name=csrf]')['value'],'mode':'view'})
        counts = store.event_counts()
        response = client.get('/?view=events')
        soup = BeautifulSoup(response.text,'html.parser')
        assert soup.h1.text == TITLE
        buttons = soup.select('.source-selectors a')
        assert int(buttons[0].select_one('.source-count').text) == sum(counts.values())
        for button, sid in zip(buttons[1:], ids):
            assert int(button.select_one('.source-count').text) == counts.get(sid,0)
        one = BeautifulSoup(client.get(buttons[1]['href']).text,'html.parser')
        assert {t.contents[0].strip() for t in one.select('.episode-camera')} == {'Front door'}
        both_url = one.select('.source-selectors a')[2]['href']
        both = BeautifulSoup(client.get(both_url).text,'html.parser')
        assert {t.contents[0].strip() for t in both.select('.episode-camera')} == {'Front door','Garden'}
        assert len(both.select('.episode-point')) == len(store.events(source_ids=tuple(ids[:2]),limit=1000))
        assert both.select_one('.episode-scroll')['tabindex'] == '0'
        assert both.select_one('script[src="/ui/episodes.js"]')
        script = client.get('/ui/episodes.js')
        assert script.status_code == 200 and script.text == EPISODES_JS
        assert "script-src 'self'" in script.headers['content-security-policy']
        assert not both.select('[data-episode-timeline] [style], [data-episode-timeline] script')
    assert {sid:store.source_control(sid) for sid in ids} == before


def test_timeline_merges_only_adjacent_active_samples_and_never_extrapolates():
    def stamp(second): return f'2026-10-26T10:00:{second:02d}+00:00'
    event = {'id':'synthetic-episode','source_id':'synthetic-camera','question_id':'q','question_version':'1',
             'started_at_utc':stamp(0),'ended_at_utc':None,'status':'open','estimated_observed_seconds':20,
             'start_observation_id':'synthetic-observation',
             'segments':[{'from':stamp(0),'to':stamp(5)},{'from':stamp(5),'to':stamp(10)},{'from':stamp(20),'to':stamp(30)}],
             'unknown_intervals':[{'from':stamp(10),'to':stamp(20)}]}
    key = ('synthetic-camera','q','1')
    soup = BeautifulSoup(to_xml(episode_timeline([event],{'synthetic-camera':'Front <door>'},{key:'Is a person visible?'},'Europe/London')),'html.parser')
    assert len(soup.select('.episode-span')) == 2 and len(soup.select('.episode-gap')) == 1
    root = soup.select_one('[data-episode-timeline]')
    assert float(root['data-end']) == utc(stamp(30)).timestamp()*1000
    assert not soup.find('door') and 'Front <door>' in soup.text
    assert soup.select_one('svg a')['href'] == '/ui/observations/synthetic-observation'
    assert '00:00:20.0' in soup.select_one('svg a')['aria-label']
    assert intervals([]) == []
    assert 'No episodes recorded' in to_xml(episode_timeline([],{}, {},'UTC'))


def test_zoom_preserves_centre_bounds_scale_and_scrolls_without_fetch_or_reload():
    node = shutil.which('node')
    if not node: pytest.skip('Node is required for the browser-script unit check')
    harness = r"""
const assert=require('node:assert/strict');
class Element {
  constructor(tag='g',dataset={}) {this.tagName=tag;this.dataset=dataset;this.attrs={};this.listeners={};}
  setAttribute(k,v){this.attrs[k]=String(v);}
  getAttribute(k){return this.attrs[k];}
  addEventListener(k,v){this.listeners[k]=v;}
  replaceChildren(...nodes){this.children=nodes;}
}
const viewport=new Element();Object.assign(viewport,{clientWidth:1000,scrollLeft:0,scrollTop:0});
const zoom=new Element(),axis=new Element(),labels=new Element(),corner=new Element(),value=new Element();
const rect=new Element('rect',{from:'100',to:'300'}),gap=new Element('line',{from:'400',to:'500'}),point=new Element('circle',{point:'0'}),row=new Element('line');
const svg=new Element('svg');svg.attrs.height='138';
svg.querySelectorAll=q=>q==='[data-from]'?[rect,gap]:q==='[data-point]'?[point]:[row];
const plus=new Element(),minus=new Element(),fit=new Element();
const selectors={'.episode-scroll':viewport,'[data-episode-svg]':svg,'#episode-zoom':zoom,'[data-episode-axis]':axis,'[data-episode-labels]':labels,'[data-episode-corner]':corner,'[data-zoom-value]':value,'[data-zoom-in]':plus,'[data-zoom-out]':minus,'[data-zoom-fit]':fit};
const root={dataset:{start:'0',end:'1000',zone:'UTC'},querySelector:q=>selectors[q]};
global.document={querySelector:()=>root,createElementNS(ns,tag){assert.equal(ns,'http://www.w3.org/2000/svg');return new Element(tag);}};
let resizeWindow,raf,frames=0;
global.window={addEventListener(name,callback){assert.equal(name,'resize');resizeWindow=callback;}};
global.requestAnimationFrame=callback=>{frames++;raf=callback;};
global.fetch=()=>{throw new Error('Zoom must never fetch/capture or reload');};
"""
    checks = r"""
assert.equal(svg.attrs.width,'1000');assert.equal(rect.attrs.x,'260');
viewport.scrollLeft=200;viewport.scrollTop=70;plus.listeners.click();
assert.equal(svg.attrs.width,'1800');assert.equal(viewport.scrollLeft,810);
assert.equal(rect.attrs.width,'320');assert.equal(gap.attrs.x1,'820');assert.equal(point.attrs.cx,'180');
assert.equal(corner.attrs.transform,'translate(810,70)');assert.equal(value.textContent,'2.0 ×');
assert.ok(axis.children.length<20); // Axis work is bounded by the viewport, not full zoom width.
zoom.value='1000';zoom.listeners.input();assert.equal(zoom.value,'64');
minus.listeners.click();assert.equal(zoom.value,'32');
fit.listeners.click();assert.equal(zoom.value,'1');assert.equal(viewport.scrollLeft,0);
viewport.listeners.scroll();viewport.listeners.scroll();assert.equal(frames,1);raf();
viewport.clientWidth=800;resizeWindow();assert.equal(svg.attrs.width,'980');
"""
    result = subprocess.run([node],input='\n'.join((harness,EPISODES_JS,checks)),capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
