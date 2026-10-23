from dataclasses import replace

from bs4 import BeautifulSoup
from starlette.testclient import TestClient

from test_phase4_worker import app, login, VIEWER
from vop.inputs.sources import capture_inline


def test_observe_answers_are_collapsible_and_isolated_per_camera(app):
    pipeline, store = app.state.pipeline, app.state.store
    first = pipeline.settings.sources[0]
    second = replace(first, source_id='second-camera', name='Garden',
                     questions=(replace(first.questions[0], text='Is the garden gate open?'),))
    store.configure(replace(pipeline.settings, sources=(second,)))
    pipeline.sources[second.source_id] = second
    pipeline.engine.configure_source_answer(second.source_id, second.questions[0].question_id, '1', False)
    with TestClient(app) as client:
        csrf = login(client)
        app.state.sampler.stop()
        pipeline.run(first.source_id, capture_inline(first))
        pipeline.run(second.source_id, capture_inline(second))
        before = store.health()['observation_count']
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        for headers in ({}, {'Authorization': 'Bearer ' + VIEWER}):
            soup = BeautifulSoup(client.get('/', headers=headers).text, 'html.parser')
            cameras = soup.select('.capture-source')
            assert len(cameras) == 2
            for camera in cameras:
                disclosure = camera.select_one('details.camera-answers')
                controls = camera.select_one('.observe-controls')
                assert disclosure.parent == controls
                assert controls.select_one('.actions').parent == controls
                assert 'open' not in disclosure.attrs
                assert disclosure.select_one('summary.button .show-answers').text == 'Show answers'
                assert disclosure.select_one('summary.button .hide-answers').text == 'Hide answers'
                assert [h.text for h in disclosure.select('th')] == ['Question', 'Episode State', 'Last answer', 'Value', 'Observed']
            assert first.questions[0].text in cameras[0].text
            assert second.questions[0].text not in cameras[0].text
            assert len(cameras[0].select('tbody tr')) == 3
            assert second.questions[0].text in cameras[1].text
            assert first.questions[0].text not in cameras[1].text
            assert len(cameras[1].select('tbody tr')) == 1
            assert cameras[0].select('tbody tr')[0].select('td')[2].text == 'Yes'
            assert cameras[1].select('tbody tr')[0].select('td')[2].text == 'No'
            assert not any(h.text == 'Latest answers' for h in soup.select('h2'))
        page = BeautifulSoup(client.get('/?source=second-camera').text, 'html.parser')
        assert len(page.select('.camera-answers')) == 1
        assert second.questions[0].text in page.select_one('.camera-answers').text
        assert store.health()['observation_count'] == before


def test_answer_fragments_refresh_scores_and_unknowns_without_capturing(app, monkeypatch):
    import json
    from datetime import timedelta
    from vop.contracts import utcnow

    sid = 'synthetic-scene'
    route = '/ui/camera-answers/' + sid
    pipeline, store = app.state.pipeline, app.state.store
    with TestClient(app) as client:
        csrf = login(client)
        app.state.sampler.stop()
        pipeline.engine.configure_source_answer(sid, 'brightness', '1', 1.25)
        pipeline.run(sid, capture_inline(pipeline.sources[sid]))
        # Explicit synthetic fixtures exercise native provider scores without a model.
        with store.connection() as db:
            for row in db.execute('SELECT id,question_id,answer_json FROM observations').fetchall():
                answer = json.loads(row['answer_json'])
                if row['question_id'] == 'red_square':
                    answer.update(score=.982, score_semantics='Liquid noul: model score for yes')
                elif row['question_id'] == 'background':
                    answer['raw_provider_fields'] = {'probabilities': {'white': .8, 'black': .2}}
                db.execute('UPDATE observations SET answer_json=? WHERE id=?', (json.dumps(answer), row['id']))
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        def fail(*_):
            raise AssertionError('Answer reads must not acquire or infer')
        monkeypatch.setattr(pipeline.capture_adapter, 'capture', fail)
        count = store.health()['observation_count']
        response = client.get(route)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, 'html.parser')
        meters = soup.select('meter')
        assert [float(m['value']) for m in meters] == [.982, .8, .2, 1.25]
        assert [float(m['max']) for m in meters] == [1, 1, 1, 2]
        assert '98.2%' in soup.text and '1.2 / 2.0' in soup.text
        assert 'Between Medium and Bright' in soup.text
        assert 'not a calibrated probability' in str(soup)
        assert response.headers['cache-control'] == 'no-store'
        tag = response.headers['etag']
        with monkeypatch.context() as patch:
            patch.setattr(store, 'summary', fail)
            unchanged = client.get(route, headers={'If-None-Match': tag})
            assert unchanged.status_code == 304 and not unchanged.content
        # Raw-score retention changes the graph even without a new observation.
        with store.connection() as db:
            row = db.execute("SELECT id,answer_json FROM observations WHERE question_id='background'").fetchone()
            answer = json.loads(row['answer_json']); answer['raw_provider_fields'] = None
            db.execute('UPDATE observations SET answer_json=? WHERE id=?', (json.dumps(answer), row['id']))
        redacted = client.get(route, headers={'If-None-Match': tag})
        assert redacted.status_code == 200
        assert 'white: Selected' in redacted.text and '80.0%' not in redacted.text
        assert client.get(route, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 200
        assert client.get('/ui/camera-answers/missing').status_code == 404
        assert client.get(route + '?zone=Invalid').status_code == 400
        future = utcnow() + timedelta(seconds=120)
        monkeypatch.setattr('vop.dashboard.utcnow', lambda: future)
        stale = client.get(route, headers={'If-None-Match': tag})
        assert stale.status_code == 200 and stale.headers['etag'] != tag
        assert not BeautifulSoup(stale.text, 'html.parser').select('meter')
        assert 'Unknown' in stale.text and 'No current value' in stale.text
        assert store.health()['observation_count'] == count
        client.cookies.clear()
        assert client.get(route).status_code == 401


def test_answer_fragment_detects_new_samples_and_history_deletion(app):
    sid = 'synthetic-scene'
    route = '/ui/camera-answers/' + sid
    with TestClient(app) as client:
        csrf = login(client)
        app.state.sampler.stop()
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        first = client.get(route)
        assert not BeautifulSoup(first.text, 'html.parser').select('meter')
        app.state.pipeline.run(sid, capture_inline(app.state.pipeline.sources[sid]))
        second = client.get(route, headers={'If-None-Match': first.headers['etag']})
        assert second.status_code == 200
        meters = BeautifulSoup(second.text, 'html.parser').select('meter')
        assert [float(m['value']) for m in meters] == [1, 1, 0, 2]
        # Retention can replace a sample with a gap at the same sequence number.
        with app.state.store.connection() as db:
            db.execute("UPDATE observations SET status='retention_gap',normalised_state='unknown',answer_json=? WHERE question_id='red_square'", ('{"value":null}',))
        deleted = client.get(route, headers={'If-None-Match': second.headers['etag']})
        assert deleted.status_code == 200
        assert len(BeautifulSoup(deleted.text, 'html.parser').select('meter')) == 3


def test_no_answer_is_an_empty_bar_but_failed_answer_has_no_bar(app):
    sid = 'synthetic-scene'
    route = '/ui/camera-answers/' + sid
    with TestClient(app) as client:
        csrf = login(client)
        app.state.sampler.stop()
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        engine, pipeline = app.state.pipeline.engine, app.state.pipeline
        engine.configure_source_answer(sid, 'red_square', '1', False)
        pipeline.run(sid, capture_inline(pipeline.sources[sid]))
        response = client.get(route)
        row = BeautifulSoup(response.text, 'html.parser').select_one('tbody tr')
        assert row.select('td')[2].text == 'No'
        assert float(row.select_one('meter')['value']) == 0
        engine.configure_source_answer(sid, 'red_square', '1', None)
        pipeline.run(sid, capture_inline(pipeline.sources[sid]))
        failed = client.get(route, headers={'If-None-Match': response.headers['etag']})
        assert failed.status_code == 200
        row = BeautifulSoup(failed.text, 'html.parser').select_one('tbody tr')
        assert row.select('td')[2].text == 'Unknown'
        assert not row.select('meter') and 'No current value' in row.text
