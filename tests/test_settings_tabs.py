from bs4 import BeautifulSoup
from starlette.testclient import TestClient

from test_phase3_release import app, HEADERS, VIEWER


def test_settings_tabs_are_distinct_and_forms_use_named_choices(app):
    with TestClient(app) as client:
        labels = ['Notifications', 'Rules', 'Export', 'Configuration and backup', 'Retention', 'Audit']
        for key, heading in zip(('notifications', 'rules', 'export', 'configuration', 'retention', 'audit'), labels):
            response = client.get('/release?tab=' + key, headers=HEADERS)
            assert response.status_code == 200
            soup = BeautifulSoup(response.text, 'html.parser')
            tabs = soup.select('nav.settings-tabs a')
            assert [a.text for a in tabs] == labels
            assert [a.text for a in tabs if a.get('aria-current') == 'page'] == [heading]
            assert 'MOCK alerts' not in response.text
            if key in ('notifications', 'export'):
                assert soup.select_one('select[name=source]')
                assert soup.select_one('select[name=question]')
                assert len(soup.select('input[type=datetime-local]')) == 2
            if key == 'rules':
                assert soup.select_one('select[name=condition] option').text.startswith('Synthetic shapes')
                assert soup.select_one('select[name=severity]')
                assert soup.select_one('select[name=rule]')
            headings = [h.text for h in soup.select('main h2')]
            if key == 'notifications':
                assert 'Rules' not in headings and 'Export' not in headings
        assert client.get('/release?tab=missing', headers=HEADERS).status_code == 400
        assert client.get('/release?tab=retention', headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 400
        style = client.get('/ui/style.css', headers=HEADERS).text
        assert '.filters .field{margin-bottom:0;' in style


def test_rule_condition_selection_generated_id_and_utc_picker_export(app):
    from test_phase2_browser_storage import login
    with TestClient(app) as client:
        # This fixture uses a different operator key.
        from test_phase3_release import TOKEN
        csrf = login(client, TOKEN)
        client.post('/ui/mode', data={'csrf': csrf, 'mode': 'configure'})
        response = client.post('/release/rules', data={'csrf': csrf, 'condition': 'synthetic-scene/red_square',
            'kind': 'duration', 'threshold': '00:01:30', 'window_seconds': '01:00:00', 'severity': 'warning',
            'enabled': '', 'webhook': ''})
        assert response.status_code == 200
        rule = app.state.reliable.rules()[0]
        assert rule['id'].startswith('rule-') and rule['source_id'] == 'synthetic-scene'
        assert rule['question_id'] == 'red_square' and rule['threshold'] == 90
        assert rule['enabled'] is False and rule['webhook'] is False
        assert client.get('/release/export?kind=events&format=json&start=2026-10-21T12:00&end=2026-10-22T12:00', headers=HEADERS).status_code == 200
        assert client.get('/release?start=invalid', headers=HEADERS).status_code == 400
