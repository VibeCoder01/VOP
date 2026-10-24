from starlette.testclient import TestClient

from test_phase4_worker import app, login, VIEWER
from vop.contracts import ProviderError


SID = 'synthetic-scene'


def test_new_names_and_image_setting_are_clear_without_changing_it(app):
    store = app.state.store
    before = store.source_control(SID)
    with TestClient(app) as client:
        csrf = login(client)
        page = client.get('/observations?source=' + SID).text
        assert '<h1>Individual Observations</h1>' in page
        assert 'Continuous Observations (Episodes)' not in page  # Configure has setup navigation only.
        assert 'Image saving is OFF' in page
        assert 'temporary capture preview is not a saved image' in page
        assert '/ui/sources/' + SID + '#image-saving' in page
        episodes = client.get('/?view=events').text
        assert '<h1>Continuous Observations (Episodes)</h1>' in episodes
        assert 'not continuous video' in episodes
        form = client.get('/ui/sources/' + SID).text
        assert 'Save images for Individual Observations' in form
        assert 'cannot recover older unsaved or deleted images' in form
        assert store.source_control(SID) == before
        capture = client.post('/ui/sources/' + SID + '/capture', data={'csrf': csrf})
        assert 'Temporary preview only. No image was saved' in capture.text
        old = store.observations()[0]
        assert not old['image_saved']
        detail = client.get('/ui/observations/' + old['id']).text
        assert 'No saved image is available' in detail
        assert 'may have been off' in detail and 'retention rule' in detail
        assert 'No image saved' in client.get('/observations?source=' + SID).text


def test_saving_images_is_future_only_visible_to_operator_and_deletable(app):
    store = app.state.store
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/ui/sources/' + SID + '/capture', data={'csrf': csrf})
        old = store.observations()[0]
        settings = {'csrf': csrf, 'enabled': 'on', 'retain_evidence': 'on', 'sample_interval_seconds': '0'}
        assert client.post('/ui/sources/' + SID, data=settings).status_code == 200
        assert not store.observation(old['id'])['image_saved']
        assert 'Image saving is ON' in client.get('/ui/observations/' + old['id']).text
        capture = client.post('/ui/sources/' + SID + '/capture', data={'csrf': csrf})
        assert 'An image was saved with this capture' in capture.text
        saved = store.observations(newest=True)[0]
        assert saved['image_saved'] is True
        detail_url = '/ui/observations/' + saved['id']
        image_url = '/ui/evidence/' + SID + '/' + saved['provenance']['frame_id']
        assert 'View saved image' in client.get('/observations?source=' + SID).text
        assert image_url in client.get(detail_url).text
        assert client.get(image_url).status_code == 200
        viewer = {'Authorization': 'Bearer ' + VIEWER}
        assert 'Operator access required' in client.get('/observations', headers=viewer).text
        detail = client.get(detail_url, headers=viewer).text
        assert image_url not in detail and 'Recorded images require operator access' in detail
        assert client.get(image_url, headers=viewer).status_code == 403
        # Turning image saving off does not delete old images.
        settings.pop('retain_evidence')
        client.post('/ui/sources/' + SID, data=settings)
        assert store.observation(saved['id'])['image_saved']
        assert image_url in client.get(detail_url).text
        client.post(image_url + '/delete', data={'csrf': csrf})
        assert not store.observation(saved['id'])['image_saved']
        assert 'No saved image is available' in client.get(detail_url).text


def test_camera_detail_links_directly_to_image_setting(app):
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/cameras/save', data={'csrf': csrf, 'model': 'C200', 'name': 'Fixture camera',
            'endpoint': 'rtsp://192.168.1.200:554/stream1', 'username': 'fixture-user', 'password': 'fixture-password'})
        before = app.state.store.source_control('tapo-c200')
        detail = client.get('/cameras/tapo-c200').text
        assert 'Image saving: Off' in detail
        assert '/cameras/tapo-c200/edit' in detail
        assert 'href="/observations' not in detail
        assert app.state.store.source_control('tapo-c200') == before


def test_capture_failure_explains_no_image_was_acquired(app, monkeypatch):
    def fail(*args):
        raise ProviderError('capture_timeout', 'Offline failure fixture')
    monkeypatch.setattr(app.state.pipeline.capture_adapter, 'capture', fail)
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/ui/sources/' + SID + '/capture', data={'csrf': csrf})
        row = app.state.store.observations()[0]
        assert row['provenance']['frame_id'] is None and not row['image_saved']
        assert 'No image captured' in client.get('/observations').text
        assert 'No image was captured' in client.get('/ui/observations/' + row['id']).text
