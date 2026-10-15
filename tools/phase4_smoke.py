"""Actual worker + dashboard HTTP smoke, protected reference and restart. Synthetic only."""
import http.cookiejar
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor

from vop.secrets import SecretStore
from process_cleanup import stop_process


def main():
    root = Path(__file__).resolve().parents[1]
    # On Linux use an injected test Secret Service fixture in the dashboard subprocess;
    # Windows exercises the real user-bound DPAPI path with disposable generated keys.
    with tempfile.TemporaryDirectory(prefix="vop-phase4-smoke-") as folder:
        folder = Path(folder)
        key = secrets.token_urlsafe(32)
        owner = secrets.token_urlsafe(32)
        secret_ref = "phase4-smoke-" + secrets.token_hex(8)
        key_path = folder / "worker.token"
        key_path.write_text(key)
        key_path.chmod(0o600)
        ports = []
        for _ in range(2):
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                ports.append(listener.getsockname()[1])
        worker_port, dashboard_port = ports
        worker = subprocess.Popen([sys.executable, str(root/"tools/run_worker.py"), "--worker-id", "smoke-worker", "--port", str(worker_port), "--token-file", str(key_path), "--backend", "mock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        body = json.loads((root/"sample-config/phase1.json").read_text(encoding="utf-8"))
        body["database"] = "data/observations.sqlite3"
        body["engine"] = {"kind": "worker", "id": "mock-worker", "version": "deterministic-mock-v1", "worker_id": "smoke-worker", "url": f"http://127.0.0.1:{worker_port}", "secret_ref": secret_ref, "transport": "local", "synthetic": True}
        config = folder/"config.json"
        config.write_text(json.dumps(body), encoding="utf-8")
        if os.name == "nt":
            # Avoid littering the user's secret store: use a disposable LOCALAPPDATA in both processes.
            vault = SecretStore(folder/"VOP/secrets")
            vault.set(secret_ref,key)
            env = {**os.environ,"LOCALAPPDATA":str(folder),"VOP_API_TOKEN":owner}
            command = [sys.executable,"-m","vop","serve","--config",str(config),"--port",str(dashboard_port),"--allow-remote-inference"]
        else:
            # This is explicitly an offline fixture, not a production plaintext-secret fallback.
            bootstrap=folder/"dashboard_fixture.py"
            bootstrap.write_text("import os\nimport uvicorn\nfrom vop.secrets import SecretStore\nSecretStore.get=lambda self,name:os.environ['VOP_SMOKE_WORKER_KEY']\nfrom vop.config import load_config\nfrom vop.service import create_app\nif __name__=='__main__':\n    app=create_app(load_config(os.environ['VOP_SMOKE_CONFIG']),allow_remote_inference=True)\n    uvicorn.run(app,host='127.0.0.1',port=int(os.environ['VOP_SMOKE_PORT']),access_log=False,log_level='warning')\n",encoding="utf-8")
            env={**os.environ,"VOP_API_TOKEN":owner,"VOP_SMOKE_WORKER_KEY":key,"VOP_SMOKE_CONFIG":str(config),"VOP_SMOKE_PORT":str(dashboard_port)}
            command=[sys.executable,str(bootstrap)]
        dashboard=None
        base=f"http://127.0.0.1:{dashboard_port}"
        def api(path,method="GET"):
            with urlopen(Request(base+path,method=method,headers={"Authorization":"Bearer "+owner}),timeout=10) as response:
                return json.load(response)
        def start():
            process=subprocess.Popen(command,cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for _ in range(200):
                try:
                    api('/api/v1/health')
                    with urlopen(Request(f'http://127.0.0.1:{worker_port}/health',headers={'Authorization':'Bearer '+key}),timeout=2) as response:
                        if json.load(response)['ready']:return process
                except (OSError,URLError):
                    if process.poll() is not None: raise RuntimeError('Dashboard failed to start')
                time.sleep(.05)
            stop_process(process)
            raise RuntimeError('Worker/dashboard startup deadline')
        try:
            dashboard=start()
            result=api('/api/v1/sources/synthetic-scene/capture','POST')['result']
            assert result['status']=='success' and result['synthetic'] and result['engine_id']=='mock-worker'
            assert result['usage']['worker']['id']=='smoke-worker'
            count=api('/api/v1/health')['observation_count']
            browser=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
            with browser.open(base+'/login') as response:html=response.read().decode()
            csrf=re.search(r'name="csrf"[^>]*value="([^"]+)"',html)[1]
            with browser.open(Request(base+'/login',data=urlencode({'csrf':csrf,'access_key':owner}).encode())) as response: response.read()
            with browser.open(base+'/integration') as response:html=response.read().decode()
            assert 'Open Cameras' in html and 'Open Engines' in html
            csrf=re.search(r'name="csrf"[^>]*value="([^"]+)"',html)[1]
            with browser.open(Request(base+'/integration/health',data=urlencode({'csrf':csrf}).encode())) as response: assert 'mock-worker' in response.read().decode()
            stop_process(dashboard);dashboard=None
            dashboard=start()
            assert api('/api/v1/health')['observation_count']==count
            stop_process(worker)
            failure=api('/api/v1/sources/synthetic-scene/capture','POST')['result']
            assert failure['status']!='success' and all(a['value'] is None for a in failure['answers'])
            print(json.dumps({'result':'PASS','worker':'explicit mock','transport':'actual loopback HTTP','persisted_observations_after_restart':count,'worker_disconnection':'UNKNOWN/ERROR without fallback','browser_health_form':'passed','windows_secret_protection':'real DPAPI' if os.name=='nt' else 'offline fixture; not OS validation','model_weights':'not_loaded','cameras':'not_connected'}))
        finally:
            for process in (dashboard,worker):
                stop_process(process)


if __name__=='__main__':
    main()
