"""Trends camera buttons preserve dates and use the configured timezone."""
from dataclasses import replace
from urllib.parse import parse_qs, urlparse, urlencode

from bs4 import BeautifulSoup
from starlette.testclient import TestClient

from test_removed_question_bulk import app, no_workers, setup_history, login, SID


def test_trends_multiselect_preserves_dates_and_replays_selected_sources_only(app, monkeypatch):
    setup_history(app)
    store, pipeline = app.state.store, app.state.pipeline
    third = replace(pipeline.sources[SID], source_id='third-fixture', name='Side gate')
    store.configure(replace(pipeline.settings, sources=(*pipeline.sources.values(), third)))
    pipeline.sources[third.source_id] = third
    before = {sid:store.source_control(sid) for sid in pipeline.sources}
    original = store.summary
    calls=[]
    def summary(sid, *args, **kwargs):
        calls.append((sid, kwargs))
        return original(sid, *args, **kwargs)
    monkeypatch.setattr(store, 'summary', summary)
    with TestClient(app) as client:
        login(client)
        def page(url):
            calls.clear()
            response=client.get(url)
            assert response.status_code==200
            soup=BeautifulSoup(response.text,'html.parser')
            assert not soup.select('select[name=source], [name=timezone]')
            assert all(kw['timezone_name']==pipeline.settings.timezone_name for _,kw in calls)
            return soup
        def labels(soup):
            return {p.text.split(' · version')[0] for p in soup.select('section p') if ' · version' in p.text}
        first=page('/?view=metrics&source='+SID+'&from=2026-10-01&through=2026-10-31&timezone=Invalid')
        assert labels(first)=={'Front door'} and {sid for sid,_ in calls}=={SID}
        assert all(kw['range_start'] and kw['range_end'] for _,kw in calls)
        buttons=first.select('nav.source-selectors a')
        second_url=buttons[2]['href']
        params=parse_qs(urlparse(second_url).query)
        assert params['from']==['2026-10-01'] and params['through']==['2026-10-31']
        assert set(params['source'])=={SID,'garden-fixture'} and 'timezone' not in params
        both=page(second_url)
        assert labels(both)=={'Front door','Garden'}
        assert {sid for sid,_ in calls}=={SID,'garden-fixture'}
        form=both.select_one('form.filters')
        assert {c['value'] for c in form.select('input[name=source]')}=={SID,'garden-fixture'}
        values=[(c['name'], c.get('value','')) for c in form.select('input[name]')]
        applied=page('/?'+urlencode(values))
        assert labels(applied)=={'Front door','Garden'}
        assert '/ui/trends-refresh.js' in str(applied)
        buttons=both.select('nav.source-selectors a')
        assert labels(page(buttons[1]['href']))=={'Garden'}
        all_url=buttons[0]['href']
        assert parse_qs(urlparse(all_url).query)['from']==['2026-10-01']
        assert labels(page(all_url))=={'Front door','Garden','Side gate'}
        assert client.get('/?view=metrics&source='+SID+'&source=missing').status_code==400
        assert client.get('/?view=metrics&from=not-a-date').status_code==400
    assert {sid:store.source_control(sid) for sid in pipeline.sources}==before
