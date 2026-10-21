import pytest
from starlette.testclient import TestClient

from test_phase2_browser_storage import settings, login, OWNER
from vop.display import duration, duration_input
from vop.service import create_app


@pytest.mark.parametrize('seconds,label', [(0, '00:00:00.0'), (59.96, '00:01:00.0'),
    (3599.96, '01:00:00.0'), (90061.2, '25:01:01.2')])
def test_duration_carries_and_round_trips(seconds, label):
    assert duration(seconds) == label
    assert duration_input(label) == pytest.approx(seconds, abs=.05)


@pytest.mark.parametrize('value', ['00:60:00', '00:00:60', '-1:00:00', 'nan', 'inf', '-1', '1:2'])
def test_invalid_durations(value):
    with pytest.raises(ValueError):
        duration_input(value)


def test_duration_forms_preserve_measurements_and_plain_labels(settings):
    app = create_app(settings, token=OWNER)
    with TestClient(app) as client:
        csrf = login(client)
        response = client.post('/ui/sources/synthetic-scene', data={'csrf': csrf,
            'enabled': 'on', 'sample_interval_seconds': '00:01:02.5'})
        assert response.status_code == 200
        assert app.state.store.source_control('synthetic-scene')['sample_interval_seconds'] == 62.5
        assert 'value="00:01:02.5"' in client.get('/ui/sources/synthetic-scene').text
        assert '>Yes/No</option>' in client.get('/ui/questions/synthetic-scene/new').text
        question = app.state.store.questions('synthetic-scene')[0]['spec']
        rule = client.post('/release/rules', data={'csrf': csrf, 'id': 'duration-format',
            'source_id': 'synthetic-scene', 'question_id': question.question_id, 'kind': 'duration',
            'threshold': '00:01:02.5', 'window_seconds': '01:00:00', 'severity': 'info', 'enabled': 'on'})
        assert rule.status_code == 200
        saved = app.state.reliable.rules()[0]
        assert saved['threshold'] == 62.5 and saved['window_seconds'] == 3600
        assert client.post('/release/retention/preview', data={'csrf': csrf, 'evidence': '24:00:00',
            'raw': '24:00:00', 'audit': '48:00:00'}).status_code == 200
        assert client.post('/release/retention/preview', data={'csrf': csrf, 'evidence': '00:30:00',
            'raw': '24:00:00', 'audit': '48:00:00'}).status_code == 400
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'view'})
        page = client.get('/?view=metrics').text
        assert 'Daily episode counts / choice dwell' not in page
        assert 'Observation coverage' in page and 'Condition active' in page
        assert 'Higher means more complete timing evidence' in page
        assert 'whether that is desirable depends on the question' in page
