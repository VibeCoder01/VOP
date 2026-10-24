from dataclasses import replace
from html.parser import HTMLParser

import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER
from vop.config import SourceSpec
from vop.dashboard import METRIC_HELP
from vop.service import create_app


class HelpParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.help = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'title' in attrs and 'aria-label' in attrs:
            self.help[attrs['title']] = attrs


def test_metric_help_is_available_on_overview_trends_and_history(app):
    with TestClient(app) as client:
        csrf = login(client)
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        parser = HelpParser()
        for path in ('/', '/?view=metrics', '/?view=events'):
            response = client.get(path)
            assert response.status_code == 200
            parser.feed(response.text)
        for label in ('Condition active', 'Observation coverage', 'Covered time',
                      'Valid samples', 'Unobserved gap', 'Estimated duration', 'Active conditions',
                      'Unknown conditions', 'Configured sources', 'Episodes recorded', 'Episode rate',
                      'Unobserved time', 'Estimated active time', 'UNKNOWN'):
            attrs = parser.help[METRIC_HELP[label]]
            assert attrs['tabindex'] == '0'
            assert attrs['aria-label'] == label + '. ' + METRIC_HELP[label]


def save_camera(client, csrf, **changes):
    return client.post('/cameras/save', data={'csrf': csrf, 'model': 'C210', 'name': 'Front door',
        'endpoint': 'rtsp://192.168.1.210:554/stream1', 'username': 'fixture-user',
        'password': 'fixture-password', **changes})


def test_camera_name_creation_rename_restart_and_model_are_independent(app, monkeypatch):
    with TestClient(app) as client:
        csrf = login(client)
        assert save_camera(client, csrf).status_code == 200
        sid = 'tapo-c210'
        assert app.state.pipeline.sources[sid].name == 'Front door'
        assert 'value="C210" selected' in client.get('/cameras/' + sid + '/edit').text
        control = app.state.store.source_control(sid)
        questions = app.state.store.questions(sid)
        secrets = dict(app.state.pipeline.sources[sid].settings)
        with monkeypatch.context() as patch:
            patch.setattr(app.state.secrets, 'get', lambda *_: pytest.fail('Renaming must not read secrets'))
            response = client.post('/cameras/' + sid + '/rename', data={'csrf': csrf, 'name': 'Garden <north>'}, follow_redirects=False)
            assert response.status_code == 303
        assert 'Garden &lt;north&gt;' in client.get(response.headers['location']).text
        assert app.state.store.source_control(sid) == control
        assert app.state.store.questions(sid) == questions
        assert app.state.pipeline.sources[sid].settings == secrets
        assert 'Garden &lt;north&gt;' in client.get('/cameras').text
        assert 'Garden &lt;north&gt;' in client.get('/').text
        restarted = create_app(app.state.pipeline.settings, token=OWNER)
        assert restarted.state.pipeline.sources[sid].name == 'Garden <north>'
        assert restarted.state.store.health()['observation_count'] == 0


def test_camera_rename_validation_permissions_and_busy(app):
    with TestClient(app) as client:
        csrf = login(client)
        save_camera(client, csrf)
        url = '/cameras/tapo-c210/rename'
        assert client.get(url, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        assert client.post(url, data={'csrf': csrf, 'name': 'Other'}, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        assert client.post(url, data={'csrf': 'wrong', 'name': 'Other'}).status_code == 403
        for name in (' ', 'x' * 129, 'Bad\nname'):
            assert client.post(url, data={'csrf': csrf, 'name': name}).status_code == 400
            assert save_camera(client, csrf, source_id='tapo-c210', name='x' * 129).status_code == 400
        app.state.pipeline.busy.acquire()
        try:
            assert client.post(url, data={'csrf': csrf, 'name': 'Other'}).status_code == 429
        finally:
            app.state.pipeline.busy.release()
        assert app.state.pipeline.sources['tapo-c210'].name == 'Front door'


def test_usb_camera_name_survives_restart(app):
    source = SourceSpec('usb-test', 'USB camera', 'usb', {'device': 0}, ())
    settings = replace(app.state.pipeline.settings, sources=(*app.state.pipeline.settings.sources, source))
    app = create_app(settings, token=OWNER)
    with TestClient(app) as client:
        csrf = login(client)
        response = client.post('/cameras/save', data={'csrf': csrf, 'source_id':'usb-test', 'name': 'Desk camera',
             'observation_settings':'1', 'enabled':'on', 'retain_evidence':'on', 'sample_interval_seconds':'00:00:15.0'})
        assert response.status_code == 200
        assert client.get('/cameras/usb-test/rename').url.path == '/cameras/usb-test'
    restarted = create_app(settings, token=OWNER)
    assert restarted.state.pipeline.sources['usb-test'].name == 'Desk camera'
    assert restarted.state.store.sources(('usb-test',))[0]['name'] == 'Desk camera'
    assert restarted.state.store.source_control('usb-test') == {'enabled':True, 'retain_evidence':True, 'sample_interval_seconds':15}
