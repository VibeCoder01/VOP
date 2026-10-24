"""Observe selection and compact camera actions; no real camera connections."""
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from starlette.testclient import TestClient

from test_removed_question_bulk import app, no_workers, setup_history, login, SID


def test_observe_multiple_camera_buttons_filter_cards_counts_and_refresh(app):
    setup_history(app)
    pipeline, store = app.state.pipeline, app.state.store
    third = replace(pipeline.sources[SID], source_id='third-fixture', name='Side gate')
    store.configure(replace(pipeline.settings, sources=(*pipeline.sources.values(), third)))
    pipeline.sources[third.source_id] = third
    controls = {sid: store.source_control(sid) for sid in pipeline.sources}
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/ui/mode', data={'csrf':csrf, 'mode':'view'})
        def page(url):
            response = client.get(url)
            assert response.status_code == 200
            soup = BeautifulSoup(response.text, 'html.parser')
            assert not soup.select('[name=timezone], select[name=source]')
            return soup
        def cards(soup):
            return [s.get_text() for s in soup.select('.capture-source > strong')]
        all_cameras = page('/?timezone=Invalid&from=invalid')
        assert cards(all_cameras) == ['Front door', 'Garden', 'Side gate']
        links = all_cameras.select('nav.source-selectors a')
        assert links[0]['aria-pressed'] == 'true'
        first = page(links[1]['href'])
        assert cards(first) == ['Front door']
        links = first.select('nav.source-selectors a')
        assert links[1]['aria-pressed'] == 'true'
        both = page(links[2]['href'])
        assert cards(both) == ['Front door', 'Garden']
        assert both.select_one('.stats .stat strong').text == '2'
        refresh = next(a['href'] for a in both.select('a') if a.text == 'Refresh view')
        assert parse_qs(urlparse(refresh).query)['source'] == [SID, 'garden-fixture']
        assert cards(page(refresh)) == cards(both)
        links = both.select('nav.source-selectors a')
        assert cards(page(links[1]['href'])) == ['Garden']
        assert cards(page(links[0]['href'])) == ['Front door', 'Garden', 'Side gate']
        assert client.get('/?source=missing&source='+SID).status_code == 400
        # Display selection does not start/pause monitoring or change camera controls.
        assert {sid: store.source_control(sid) for sid in pipeline.sources} == controls


def test_camera_setup_actions_have_consistent_buttons_and_compact_rows(app):
    with TestClient(app) as client:
        csrf = login(client)
        response = client.post('/cameras/save', data={'csrf':csrf, 'source_id':'tapo-c200', 'model':'C200',
             'name':'Front door', 'endpoint':'rtsp://192.168.1.100:554/stream1',
             'username':'offline-fixture', 'password':'offline-fixture'})
        assert response.status_code == 200
        soup = BeautifulSoup(client.get('/cameras').text, 'html.parser')
        row = soup.select_one('.camera-list .object-row')
        actions = row.select('.actions a')
        assert [a.text for a in actions] == ['Manage camera']
        assert all('button' in a['class'] for a in actions)
        assert 'camera-list .object-row{padding:12px 0' in client.get('/ui/style.css').text
