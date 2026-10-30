"""Browser modes are explicit and do not change the operator's evidence permissions."""
from starlette.testclient import TestClient

from test_phase2_browser_storage import settings, OWNER, VIEWER, csrf
from vop.service import create_app


def sign_in(client, key=OWNER):
    token = csrf(client)
    response = client.post('/login', data={'csrf': token, 'access_key': key})
    assert response.status_code == 200
    return csrf(client, '/')


def test_default_view_switch_and_configuration_guard(settings):
    app = create_app(settings, token=OWNER, viewer_token=VIEWER)
    with TestClient(app) as client:
        token = sign_in(client)
        controls = app.state.store.source_control('synthetic-scene')
        home = client.get('/').text
        assert 'View mode' in home and 'Switch to Configure mode' in home
        assert 'Manage cameras' not in home and 'Run synthetic demo' not in home
        assert 'href="/engines"' not in home and 'href="/?view=questions"' not in home
        assert 'Capture once' in home
        for path in ('/cameras', '/engines', '/?view=questions', '/?view=settings',
                     '/?view=metrics&view=questions', '/ui/sources/synthetic-scene', '/release',
                     '/engines/example.js', '/ui/observations/missing/delete'):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 303 and response.headers['location'] == '/configure'
        assert 'Switch to Configure mode' in client.get('/configure').text
        for path in ('/ui/replay', '/ui/restart',
                     '/ui/questions/synthetic-scene/red_square'):
            response = client.post(path, data={'csrf': token})
            assert response.status_code == 403 and response.json()['error'] == 'configure_mode_required'
        assert client.post('/ui/mode', data={'mode': 'configure'}).status_code == 403
        stale = client.post('/ui/replay', data={'csrf': token}, headers={'Accept': 'text/html'})
        assert 'No changes were saved.' in stale.text and 'Switch to Configure mode' in stale.text
        assert client.post('/ui/mode', data={'csrf': token, 'mode': 'invalid'}).status_code == 400
        assert client.post('/ui/mode', data={'csrf': token, 'mode': 'configure'}).status_code == 200
        assert 'Configure mode' in client.get('/cameras').text
        assert client.get('/').url.path == '/cameras'
        assert 'Manage cameras' not in client.get('/').text
        assert client.post('/ui/mode', data={'csrf': token, 'mode': 'view'}).status_code == 200
        assert 'View mode' in client.get('/?view=metrics').text
        assert app.state.store.source_control('synthetic-scene') == controls
        # Existing authenticated API clients do not acquire a browser mode.
        assert client.get('/engines', headers={'Authorization': 'Bearer '+OWNER}).status_code == 200


def test_view_keeps_observations_and_images_but_hides_deletion(settings):
    app = create_app(settings, token=OWNER)
    store, pipeline = app.state.store, app.state.pipeline
    store.update_source('synthetic-scene', enabled=True, retain_evidence=True, sample_interval_seconds=0)
    pipeline.run('synthetic-scene')
    observation = store.observations()[0]
    with TestClient(app) as client:
        token = sign_in(client)
        listing = client.get('/observations?source=synthetic-scene').text
        assert 'View saved image' in listing
        assert 'Delete capture…' not in listing and 'Delete input history…' not in listing
        assert 'Change image-saving setting' not in listing
        detail = client.get('/ui/observations/'+observation['id']).text
        assert 'Delete saved image' not in detail and 'Delete this capture' not in detail
        frame = observation['provenance']['frame_id']
        image = '/ui/evidence/synthetic-scene/'+frame
        assert client.get(image).status_code == 200
        assert client.post(image+'/delete', data={'csrf': token}).status_code == 403
        # Capture remains an explicit user action in View mode.
        capture = client.post('/ui/sources/synthetic-scene/capture', data={'csrf': token})
        assert capture.status_code == 200 and 'Delete capture…' not in capture.text
        assert client.post('/ui/mode', data={'csrf': token, 'mode': 'configure'}).status_code == 200
        assert 'Delete saved image' in client.get('/ui/observations/'+observation['id']).text
        token = sign_in(client)
        assert 'View mode' in client.get('/').text  # Fresh sign-in resets the mode.


def test_viewer_cannot_enter_configure_and_launcher_defaults_to_view(settings):
    with TestClient(create_app(settings, token=OWNER, viewer_token=VIEWER)) as client:
        token = sign_in(client, VIEWER)
        assert 'Switch to Configure mode' not in client.get('/').text
        assert client.post('/ui/mode', data={'csrf': token, 'mode': 'configure'}).status_code == 403
        assert client.get('/engines').status_code == 403
        ticket = client.post('/api/v1/browser-ticket', headers={'Authorization': 'Bearer '+OWNER}).json()['url']
        assert 'View mode' in client.get(ticket).text


def test_one_mode_toggle_and_no_observe_in_configure_or_duplicate_history(settings):
    from bs4 import BeautifulSoup
    app = create_app(settings, token=OWNER)
    app.state.pipeline.run('synthetic-scene')
    with TestClient(app) as client:
        token = sign_in(client)
        def mode_form(path, label):
            page = BeautifulSoup(client.get(path).text, 'html.parser')
            forms = page.find_all('form', action='/ui/mode')
            assert len(forms) == 1
            group = page.select_one('.mode-switch[role=group]')
            assert group['aria-label'] == 'Workspace mode'
            assert forms[0].parent == group
            assert group.select_one('.mode-label[role=status]')
            assert forms[0].find('button').get_text() == label
            return page
        home = mode_form('/', 'Configure mode')
        assert home.find('h1').get_text() == 'Observe'
        assert 'Recent Individual Observations' not in home.get_text()
        assert 'Individual Observations' in client.get('/observations').text
        mode_form('/configure', 'Configure mode')
        client.post('/ui/mode', data={'csrf': token, 'mode': 'configure'})
        configuration = mode_form('/cameras', 'View mode')
        assert [a.get_text() for a in configuration.find('nav').find_all('a')] == ['Questions', 'Actions', 'Automations', 'Cameras', 'Engines', 'Settings', 'Diagnostics']
        for path in ('/?view=questions', '/?view=settings'):
            links = BeautifulSoup(client.get(path).text, 'html.parser').find('nav').find_all('a')
            assert [a.get_text() for a in links] == ['Questions', 'Actions', 'Automations', 'Cameras', 'Engines', 'Settings', 'Diagnostics']
        assert 'Manage saved data' in client.get('/?view=settings').text
        assert configuration.find('a', class_='brand')['href'] == '/cameras'
        assert client.get('/').url.path == '/cameras'
        client.post('/ui/mode', data={'csrf': token, 'mode': 'view'})
        assert client.get('/').url.path == '/'
        mode_form('/', 'Configure mode')
