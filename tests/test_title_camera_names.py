from dataclasses import replace
from importlib.metadata import version

from starlette.testclient import TestClient

from test_phase4_worker import app, login


def test_version_and_camera_names_in_observation_views_with_id_fallback(app):
    pipeline, store = app.state.pipeline, app.state.store
    sid = 'synthetic-scene'

    def rename(name):
        source = replace(pipeline.sources[sid], name=name)
        store.configure(replace(pipeline.settings, sources=(source,)))
        pipeline.sources[sid] = source

    rename('Front <door>')
    with TestClient(app) as client:
        assert 'class="app-version"' in client.get('/login').text
        csrf = login(client)
        for _ in range(2):
            capture = client.post('/ui/sources/' + sid + '/capture', data={'csrf': csrf})
            assert '<p>Front &lt;door&gt;</p>' in capture.text
        observation = store.observations()[0]
        for path in ('/', '/observations', '/?view=events', '/ui/observations/' + observation['id']):
            page = client.get(path).text
            assert 'class="app-version"' in page and 'v' + version('vop') in page
            assert 'VOP version ' + version('vop') in page
            assert '· VOP v' + version('vop') + '</title>' in page
            assert 'Front &lt;door&gt;' in page
        assert '<small>Front &lt;door&gt;</small>' in client.get('/observations').text
        assert '<small>Front &lt;door&gt; · version 1</small>' in client.get('/?view=events').text
        rename('')
        assert '<small>synthetic-scene</small>' in client.get('/observations').text
        assert '<p>synthetic-scene /' in client.get('/ui/observations/' + observation['id']).text
