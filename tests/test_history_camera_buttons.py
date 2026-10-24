"""History multi-selection uses synthetic records; no camera/model connections."""
from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_removed_question_bulk import app, no_workers, setup_history, login, SID
from vop.contracts import utcnow
from vop.inputs.sources import capture_inline
from vop.storage import dumps


def history(app):
    setup_history(app)
    store, pipeline = app.state.store, app.state.pipeline
    third = replace(pipeline.sources[SID], source_id='third-fixture', name='Side gate')
    store.configure(replace(pipeline.settings, sources=(*pipeline.sources.values(), third)))
    pipeline.sources[third.source_id] = third
    store.update_source(third.source_id, enabled=True, retain_evidence=False, sample_interval_seconds=0)
    pipeline.run(third.source_id, capture_inline(third))
    ids = list(pipeline.sources)
    with store.connection() as db:
        templates = {sid:db.execute('SELECT id FROM observations WHERE source_id=? LIMIT 1',(sid,)).fetchone()[0] for sid in ids}
        for i in range(180):
            sid=ids[i%3]
            db.execute('''INSERT INTO observations(id,run_id,source_id,question_id,question_version,captured_at_utc,processed_at_utc,status,normalised_state,answer_json)
                          SELECT ?,run_id,source_id,question_id,question_version,captured_at_utc,processed_at_utc,status,normalised_state,answer_json FROM observations WHERE id=?''',
                       ('history-fixture-'+str(i),templates[sid]))
            stamp=(utcnow()+timedelta(seconds=i)).isoformat()
            event={'id':'episode-fixture-'+str(i),'source_id':sid,'question_id':'red_square','question_version':'1',
                   'started_at_utc':stamp,'ended_at_utc':None,'status':'open','estimated_observed_seconds':1,
                   'unknown_seconds':0,'start_observation_id':templates[sid]}
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)',(event['id'],sid,'red_square','1',stamp,dumps(event)))
    return ids


@pytest.mark.parametrize('url', ['/observations','/?view=events'])
def test_history_buttons_multiselect_reset_and_invalid_sources(app, url):
    ids=history(app)
    before={sid:app.state.store.source_control(sid) for sid in ids}
    with TestClient(app) as client:
        login(client)
        def page(path):
            response=client.get(path)
            assert response.status_code==200
            soup=BeautifulSoup(response.text,'html.parser')
            assert not soup.select('select[name=source], [name=timezone]')
            return soup
        def labels(soup):
            return {s.text.split(' · version')[0] for s in soup.select('.table-wrap tbody tr td:first-child small')}
        all_cameras=page(url)
        buttons=all_cameras.select('nav.source-selectors a')
        assert [b.text for b in buttons]==['All cameras','Front door','Garden','Side gate']
        one=page(buttons[1]['href'])
        assert labels(one)=={'Front door'}
        buttons=one.select('nav.source-selectors a')
        both=page(buttons[2]['href'])
        assert labels(both)=={'Front door','Garden'}
        buttons=both.select('nav.source-selectors a')
        assert buttons[1]['aria-pressed']==buttons[2]['aria-pressed']=='true'
        assert labels(page(buttons[1]['href']))=={'Garden'}
        assert labels(page(buttons[0]['href']))=={'Front door','Garden','Side gate'}
        separator='&' if '?' in url else '?'
        assert client.get(url+separator+'source=missing&source='+SID).status_code==400
        if 'events' in url:
            assert page(url+'&timezone=Invalid').select_one('h1').text=='Continuous Observations (Episodes)'
        else:
            older=next(a['href'] for a in both.select('a') if a.text=='Older answers')
            assert set(parse_qs(urlparse(older).query)['source'])==set(ids[:2])
            assert labels(page(older))=={'Front door','Garden'}
            assert client.get('/observations?before=0').status_code==400
    assert {sid:app.state.store.source_control(sid) for sid in ids}==before


def test_storage_multiselect_filters_before_global_order_and_limit(app):
    ids=history(app)
    store=app.state.store
    selected=tuple(ids[:2])
    answers=store.observations(source_ids=selected,newest=True,limit=100)
    assert len(answers)==100 and {o['source_id'] for o in answers}==set(selected)
    assert [o['sequence'] for o in answers]==sorted((o['sequence'] for o in answers),reverse=True)
    older=store.observations(source_ids=selected,newest=True,before=answers[-1]['sequence'],limit=100)
    assert older and max(o['sequence'] for o in older)<answers[-1]['sequence']
    assert not {o['id'] for o in answers}&{o['id'] for o in older}
    episodes=store.events(source_ids=selected,limit=100)
    assert len(episodes)==100 and {e['source_id'] for e in episodes}==set(selected)
    assert [e['started_at_utc'] for e in episodes]==sorted((e['started_at_utc'] for e in episodes),reverse=True)
