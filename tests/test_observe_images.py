from dataclasses import replace
from io import BytesIO

from bs4 import BeautifulSoup
from PIL import Image
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER
from vop.inputs.sources import capture_inline


def test_observe_keeps_each_latest_masked_image_and_tracks_monitoring(app, monkeypatch):
    pipeline, store = app.state.pipeline, app.state.store
    first = replace(pipeline.settings.sources[0], settings={'privacy_masks': [[0, 0, .5, 1]]})
    second = replace(first, source_id='second-scene', name='Second fixture', settings={})
    store.configure(replace(pipeline.settings, sources=(first, second)))
    pipeline.sources.update({first.source_id: first, second.source_id: second})
    with TestClient(app) as client:
        csrf = login(client)
        app.state.sampler.stop()
        pipeline.run(first.source_id, capture_inline(first))
        pipeline.run(second.source_id, capture_inline(second))
        first_id = pipeline.previews[first.source_id][0]
        second_id = pipeline.previews[second.source_id][0]
        assert pipeline.latest_preview[0] == second.source_id
        store.update_source(first.source_id, enabled=True, retain_evidence=False, sample_interval_seconds=10)
        def fail(*_):
            raise AssertionError('Preview reads must never acquire another frame')
        monkeypatch.setattr(pipeline.capture_adapter, 'capture', fail)
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        soup = BeautifulSoup(client.get('/').text, 'html.parser')
        cards = soup.select('[data-observe-preview]')
        assert len(cards) == 2
        assert 'monitoring' in cards[0]['class'] and 'monitoring' not in cards[1]['class']
        assert cards[0].select_one('img')['src'].endswith(first.source_id)
        assert '/ui/observe-images.js' in str(soup)
        response = client.get('/ui/live-preview/' + first.source_id)
        assert response.status_code == 200 and response.headers['x-vop-frame-id'] == first_id
        assert response.headers['x-vop-monitoring'] == 'true'
        assert response.headers['cache-control'] == 'no-store'
        assert Image.open(BytesIO(response.content)).convert('RGB').getpixel((0, 0)) == (0, 0, 0)
        assert store.evidence(first.source_id, first_id) is None
        head = client.head('/ui/live-preview/' + second.source_id)
        assert head.status_code == 200 and not head.content
        assert int(head.headers['content-length']) == len(client.get('/ui/live-preview/' + second.source_id).content)
        assert head.headers['x-vop-frame-id'] == second_id and head.headers['x-vop-monitoring'] == 'false'
        assert client.get('/ui/preview/' + first.source_id + '/' + first_id).status_code == 200
        count = store.health()['observation_count']
        store.update_source(first.source_id, enabled=True, retain_evidence=False, sample_interval_seconds=0)
        assert client.head('/ui/live-preview/' + first.source_id).headers['x-vop-monitoring'] == 'false'
        assert client.get('/ui/live-preview/' + first.source_id).content == response.content
        pipeline.clear_preview(first.source_id)
        assert client.head('/ui/live-preview/' + first.source_id).status_code == 204
        assert client.get('/ui/live-preview/' + second.source_id).status_code == 200
        assert store.health()['observation_count'] == count
        for method in (client.get, client.head):
            assert method('/ui/live-preview/' + second.source_id, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        assert client.get('/ui/live-preview/missing').status_code == 404


def test_saved_image_fallback_is_labelled_and_deletion_does_not_resurface_it(app):
    sid = 'synthetic-scene'
    with TestClient(app) as client:
        login(client)
        app.state.sampler.stop()
        store, pipeline = app.state.store, app.state.pipeline
        store.update_source(sid, enabled=True, retain_evidence=True, sample_interval_seconds=0)
        result = pipeline.run(sid)
        frame_id = result['result']['frame_id']
        pipeline.latest_preview = None
        response = client.get('/ui/live-preview/' + sid)
        assert response.status_code == 200 and response.headers['x-vop-preview-kind'] == 'saved'
        assert response.headers['x-vop-frame-id'] == frame_id
        assert client.post('/ui/evidence/' + sid + '/' + frame_id + '/delete', headers={'Authorization': 'Bearer ' + OWNER}).status_code == 200
        assert client.head('/ui/live-preview/' + sid).status_code == 204
        assert client.get('/ui/live-preview/' + sid).status_code == 404


def test_camera_test_actions_are_separate_from_the_image(app):
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/integration/camera', data={'csrf': csrf, 'source_id': 'tapo-c200', 'model': 'C200',
            'endpoint': 'rtsp://192.168.1.100:554/stream1', 'username': 'fixture', 'password': 'fixture'})
        soup = BeautifulSoup(client.get('/integration/cameras/tapo-c200/test').text, 'html.parser')
        footer = soup.select_one('.camera-test-actions')
        assert footer.select_one('form button').text == 'Test camera again'
        assert footer.select_one('a.button.secondary').text == 'Back to camera'
        assert not footer.select('img')
        assert footer.find_previous_sibling()['class'] == ['camera-test-result']
