"""Real launcher and interpreter restarts on a disposable loopback mock workspace."""
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

from run_dashboard import stop_existing
from process_cleanup import stop_process


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='vop-restart-smoke-') as folder:
        folder = Path(folder)
        config = json.loads((root / 'sample-config/phase1.json').read_text())
        config['database'] = 'test.sqlite3'
        path = folder / 'config.json'
        path.write_text(json.dumps(config))
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        token = secrets.token_urlsafe(32)
        env = {**os.environ, 'VOP_API_TOKEN': token, 'LOCALAPPDATA': str(folder),
               'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1'}
        command = [sys.executable, str(root / 'tools/run_dashboard.py'), str(path), '--port', str(port), '--manual-worker']
        processes = []

        def api(route, method='GET'):
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
            try:
                connection.request(method, route, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
                response = connection.getresponse()
                payload = json.loads(response.read())
                assert response.status in (200, 201, 202), (response.status, payload)
                return payload
            finally:
                connection.close()

        def ready(previous=None):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    health = api('/api/v1/health')
                    if health['instance_id'] != previous:
                        return health
                except (OSError, http.client.HTTPException):
                    pass
                time.sleep(.2)
            raise RuntimeError('Fresh dashboard did not become ready')

        try:
            processes.append(subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            first = ready()
            api('/api/v1/sources/synthetic-scene/capture', 'POST')
            count = api('/api/v1/health')['observation_count']
            assert count == 3
            api('/ui/restart', 'POST')
            second = ready(first['instance_id'])
            assert second['observation_count'] == count
            processes.append(subprocess.Popen([*command, '--restart-existing'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            third = ready(second['instance_id'])
            assert third['observation_count'] == count
            api('/api/v1/shutdown', 'POST')
            print(json.dumps({'result': 'PASS', 'gui_restart': 'fresh interpreter and instance',
                              'launcher_restart': 'old instance replaced', 'retained_observations': count,
                              'retained_access_key': True, 'bind': '127.0.0.1',
                              'cameras': 'not_connected', 'model_weights': 'not_loaded'}))
        finally:
            stop_existing(port, token, graceful_seconds=10)
            for process in processes:
                stop_process(process)


if __name__ == '__main__':
    main()
