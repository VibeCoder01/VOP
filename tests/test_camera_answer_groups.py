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
                assert 'open' not in disclosure.attrs
                assert disclosure.select_one('summary.button .show-answers').text == 'Show answers'
                assert disclosure.select_one('summary.button .hide-answers').text == 'Hide answers'
                assert [h.text for h in disclosure.select('th')] == ['Question', 'State', 'Last answer', 'Observed']
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
