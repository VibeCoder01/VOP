from dataclasses import replace
from importlib.metadata import version
from html.parser import HTMLParser

from starlette.testclient import TestClient

from test_phase4_worker import app, login


class VersionPlacement(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_brand = False
        self.in_main = False
        self.brand_version = False
        self.main_version = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('class') == 'brand': self.in_brand = True
        if tag == 'main': self.in_main = True
        if attrs.get('class') == 'app-version':
            self.brand_version |= self.in_brand
            self.main_version |= self.in_main

    def handle_endtag(self, tag):
        if tag == 'a': self.in_brand = False
        if tag == 'main': self.in_main = False


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
        for path in ('/', '/observations', '/?view=events', '/?view=metrics', '/ui/observations/' + observation['id']):
            page = client.get(path).text
            assert 'class="app-version"' in page and 'v' + version('vop') in page
            assert 'VOP version ' + version('vop') in page
            assert '· VOP v' + version('vop') + '</title>' in page
            assert 'Front &lt;door&gt;' in page
            placement = VersionPlacement()
            placement.feed(page)
            assert placement.brand_version and not placement.main_version
        assert '<small>Front &lt;door&gt;</small>' in client.get('/observations').text
        assert '<small>Front &lt;door&gt; · version 1</small>' in client.get('/?view=events').text
        assert '<p>Front &lt;door&gt; · version 1 · binary</p>' in client.get('/?view=metrics').text
        rename('')
        assert '<small>synthetic-scene</small>' in client.get('/observations').text
        assert '<p>synthetic-scene /' in client.get('/ui/observations/' + observation['id']).text
        assert '<p>synthetic-scene · version 1 · binary</p>' in client.get('/?view=metrics').text
