from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from test_phase4_worker import app, login, OWNER, VIEWER
from tools import run_dashboard


def test_restart_requires_operator_csrf_and_managed_launcher(app):
    calls = []
    with TestClient(app) as client:
        assert client.post('/ui/restart').status_code == 401
        csrf = login(client)
        assert client.post('/ui/restart', data={'csrf': csrf}).status_code == 409
        app.state.shutdown_request = calls.append
        for path in ('/ui/restart', '/api/v1/shutdown'):
            assert client.post(path, data={'csrf': 'wrong'}).status_code == 403
            assert client.post(path, headers={'Authorization': 'Bearer ' + VIEWER}).status_code == 403
        assert client.get('/ui/restart').status_code == 405
        assert not calls
        page = client.get('/?view=settings').text
        assert 'Restart VOP' in page and 'data-vop-restart' in page and '/ui/restart.js' in page
        response = client.post('/ui/restart', data={'csrf': csrf}, headers={'Accept': 'application/json'})
        assert response.status_code == 202 and response.json()['instance_id'] == app.state.instance_id
        assert calls == ['restart']
        assert client.post('/api/v1/shutdown', headers={'Authorization': 'Bearer ' + OWNER}).status_code == 202
        assert calls == ['restart', 'stop']


def test_managed_restart_stops_new_sampling_before_exiting(app, monkeypatch):
    class Server:
        def __init__(self, config): self.should_exit = False
        def run(self):
            app.state.shutdown_request('restart')
            app.state.shutdown_request('stop')  # First request wins.
            assert self.should_exit
            assert app.state.sampler.stop_event.is_set()
            assert app.state.reliable.stop_event.is_set()
            with pytest.raises(Exception, match='application_stopping'):
                app.state.pipeline.run('synthetic-scene')
    monkeypatch.setattr(run_dashboard.uvicorn, 'Server', Server)
    assert run_dashboard.managed_run(app, 8765)
    assert app.state.store.health()['observation_count'] == 0


def test_shutdown_request_is_not_blocked_by_capture_admission(app):
    from threading import Event, Thread
    from vop.contracts import ProviderError
    entered, release = Event(), Event()
    original = app.state.pipeline.run
    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        raise ProviderError('capture_timeout', 'Offline blocked capture')
    app.state.pipeline.run = blocked
    calls = []
    app.state.shutdown_request = calls.append
    with TestClient(app) as client:
        thread = Thread(target=lambda: client.post('/api/v1/sources/synthetic-scene/capture', headers={'Authorization': 'Bearer ' + OWNER}))
        thread.start()
        try:
            assert entered.wait(2)
            assert client.post('/api/v1/shutdown', headers={'Authorization': 'Bearer ' + OWNER}).status_code == 202
            assert calls == ['stop']
        finally:
            release.set()
            thread.join(5)
            app.state.pipeline.run = original


def test_owned_dashboard_matches_installation_runtime_account_and_port(monkeypatch, tmp_path):
    account = run_dashboard.psutil.Process().username()
    command = [sys.executable, str(Path(run_dashboard.__file__).resolve()), '--port', '9876']
    process = SimpleNamespace(username=lambda: account, exe=lambda: sys.executable,
                              cmdline=lambda: command, cwd=lambda: str(tmp_path))
    assert run_dashboard.owned_dashboard(process, 9876)
    assert not run_dashboard.owned_dashboard(process, 8765)
    command[1] = str(tmp_path / 'run_dashboard.py')
    assert not run_dashboard.owned_dashboard(process, 9876)
    command[1] = str(Path(run_dashboard.__file__).resolve())
    process.username = lambda: 'another-account'
    assert not run_dashboard.owned_dashboard(process, 9876)
    process.username = lambda: account
    process.exe = lambda: str(tmp_path / 'python.exe')
    assert not run_dashboard.owned_dashboard(process, 9876)


def test_stale_cleanup_excludes_launcher_ancestors_and_unrelated_processes(monkeypatch):
    calls = []
    class Process:
        def __init__(self, pid): self.pid = pid
        def is_running(self): return True
        def children(self, recursive=True): return []
        def terminate(self): calls.append(self.pid)
    me, parent, stale, unrelated = (Process(i) for i in (1, 2, 3, 4))
    me.parents = lambda: [parent]
    monkeypatch.setattr(run_dashboard.os, 'getpid', lambda: 1)
    monkeypatch.setattr(run_dashboard.psutil, 'Process', lambda: me)
    monkeypatch.setattr(run_dashboard.psutil, 'process_iter', lambda: [me, parent, stale, unrelated])
    monkeypatch.setattr(run_dashboard, 'owned_dashboard', lambda p, port: p.pid != 4)
    monkeypatch.setattr(run_dashboard, 'trusted_listener', lambda port: False)
    monkeypatch.setattr(run_dashboard.psutil, 'wait_procs', lambda *a, **k: ([], []))
    monkeypatch.setattr(run_dashboard.http.client, 'HTTPConnection', lambda *a, **k: pytest.fail('Never send a key to an unrelated listener'))
    run_dashboard.stop_existing(0, OWNER)
    assert calls == [3]


def test_unknown_port_owner_is_not_stopped(monkeypatch):
    monkeypatch.setattr(run_dashboard.psutil, 'process_iter', lambda: [])
    monkeypatch.setattr(run_dashboard, 'trusted_listener', lambda port: False)
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def setsockopt(self, *args): pass
        def bind(self, address): raise OSError('busy')
    monkeypatch.setattr(run_dashboard.socket, 'socket', Socket)
    with pytest.raises(RuntimeError, match='unrelated process was left running'):
        run_dashboard.stop_existing(9876, OWNER)
