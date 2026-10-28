"""Local launcher sign-in and bounded, on-demand recovery for the established pilot."""
import secrets
import shutil
import os
import subprocess
from threading import Lock
from time import monotonic, sleep

from starlette.responses import JSONResponse, RedirectResponse, Response

from vop.contracts import ProviderError
from vop.inference.remote import RemoteInferenceEngine
from vop.inference.liquid_d1 import CHECKPOINT_REVISION
from vop.worker_session import antec_target


def is_antec(engine):
    return (isinstance(engine, RemoteInferenceEngine) and engine.engine_id == 'liquid-d1-3b'
            and engine.engine_version == CHECKPOINT_REVISION and not engine.synthetic
            and engine.config['worker_id'] == 'antec-d1' and engine.config['transport'] == 'ssh'
            and engine.config['url'] == 'http://127.0.0.1:8878')


def install_local_login(app, store):
    tickets, lock = {}, Lock()

    @app.route('/api/v1/browser-ticket', methods=['POST'])
    def browser_ticket(request):
        if request.scope.get('auth_role') != 'operator' or not request.headers.get('authorization', '').startswith('Bearer '):
            return JSONResponse({'error': 'launcher_authentication_required'}, status_code=403)
        ticket = secrets.token_urlsafe(32)
        with lock:
            tickets.clear()  # Only the most recent local launch remains valid, for one minute.
            tickets[ticket] = monotonic() + 60
        return JSONResponse({'url': '/launch/' + ticket})

    @app.route('/launch/{ticket}', methods=['GET'])
    def launch(ticket: str, request):
        with lock:
            expiry = tickets.pop(ticket, 0)
        if expiry < monotonic():
            return Response('This launch link expired. Open Start VOP again to sign in automatically.', status_code=401)
        request.scope['session'].clear()
        request.scope['session'].update(role='operator', csrf=secrets.token_urlsafe(24))
        store.audit('launcher_login', 'accepted')
        return RedirectResponse('/', status_code=303, headers={'Referrer-Policy': 'no-referrer'})


class AutoWorker:
    def __init__(self, pipeline, session, store, *, wait_seconds=30):
        self.pipeline, self.session, self.store = pipeline, session, store
        self.wait_seconds = wait_seconds
        self.lock = Lock()
        self.last_failure = None
        self.retry_after = 0

    def recover_key(self, engine):
        ssh = shutil.which('ssh.exe' if os.name == 'nt' else 'ssh')
        if not ssh:
            raise ProviderError('ssh_missing', 'VOP needs SSH installed to reconnect to Antec')
        try:
            host, identity_options = antec_target()
            result = subprocess.run([ssh, '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                                     '-o', 'ConnectTimeout=5', *identity_options, host,
                                     'head -c 257 ~/.local/share/vop/phase4/worker.token'],
                                    capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            key = result.stdout.decode('ascii').strip()
            if result.returncode or not 32 <= len(key) <= 256 or any(c.isspace() for c in key):
                raise ValueError()
            engine.secrets.set(engine.config['secret_ref'], key)
        except (OSError, ValueError, subprocess.SubprocessError):
            raise ProviderError('worker_reconnect_failed', 'VOP could not reconnect securely to Antec. Check it is awake and reachable, then retry') from None
        self.store.audit('worker_key', 'recovered_from_trusted_antec')

    def ensure_ready(self):
        engine = self.pipeline.engine
        if not is_antec(engine):
            if isinstance(engine, RemoteInferenceEngine):
                health = engine.health()
                if not health.get('ready') or health.get('busy'):
                    raise ProviderError('worker_unavailable', 'The selected worker is not ready')
            return  # Never change another backend, identity, model or deployment.
        if not self.lock.acquire(False):
            raise ProviderError('recovery_busy', 'VOP is already connecting to Antec. Retry shortly')
        started = False
        try:
            if monotonic() < self.retry_after and self.last_failure:
                raise self.last_failure
            try:
                health = engine.health()
            except ProviderError as exc:
                if exc.code not in ('secret_unavailable', 'worker_auth', 'worker_unavailable'):
                    raise
                if exc.code in ('secret_unavailable', 'worker_auth'):
                    self.recover_key(engine)
                    try:
                        health = engine.health()
                    except ProviderError as retry:
                        if retry.code != 'worker_unavailable':
                            raise
                        health = None
                else:
                    health = None
            if health and health.get('ready'):
                if health.get('busy'):
                    raise ProviderError('overloaded', 'Antec is processing another observation. Retry shortly')
                engine.allow_remote = True
                self.last_failure, self.retry_after = None, 0
                return
            code = health.get('error') if health else None
            if isinstance(code, str) and code in ('gpu_capacity', 'host_capacity', 'device_mismatch', 'model_load_failed'):
                raise ProviderError(code, 'Antec could not load the selected model')
            if not self.session.status()['active']:
                self.session.start(15)
                started = True
                self.store.audit('automatic_worker', 'timed_session_requested')
            deadline = monotonic() + self.wait_seconds
            while monotonic() < deadline:
                try:
                    health = engine.health()
                    if health.get('ready'):
                        if health.get('busy'):
                            raise ProviderError('overloaded', 'Antec is processing another observation. Retry shortly')
                        engine.allow_remote = True
                        self.last_failure, self.retry_after = None, 0
                        return
                    code = health.get('error')
                    if isinstance(code, str) and code in ('gpu_capacity', 'host_capacity', 'device_mismatch', 'model_load_failed'):
                        raise ProviderError(code, 'Antec could not load the selected model')
                except ProviderError as exc:
                    if exc.code in ('secret_unavailable', 'worker_auth'):
                        self.recover_key(engine)
                    elif exc.code != 'worker_unavailable':
                        raise
                if not self.session.status()['active']:
                    raise ProviderError('worker_reconnect_failed', 'The connection to Antec closed before the worker became ready')
                sleep(.5)
            raise ProviderError('worker_starting', 'Antec is still getting ready. Wait a moment, then retry; VOP will reuse the same session')
        except ProviderError as exc:
            if started and exc.code not in ('worker_starting', 'overloaded'):
                try:
                    self.session.stop()
                except (OSError, subprocess.SubprocessError):
                    self.store.audit('automatic_worker_cleanup', 'confirmation_unavailable')
            self.last_failure, self.retry_after = exc, monotonic() + 5
            raise
        finally:
            self.lock.release()


def recovery_message(code):
    return {
        'secret_unavailable': 'Windows could not unlock the saved settings. Close VOP and reopen Start VOP under the same Windows account.',
        'worker_auth': 'VOP could not authenticate with Antec. Retry to recover the saved connection automatically.',
        'worker_unavailable': 'Antec is not reachable. Check it is switched on and connected to the network, then retry.',
        'worker_starting': 'Antec is still loading the model. Wait a moment and retry.',
        'tunnel_in_use': 'Another connection is using the Antec port. Check the existing worker connection before starting another.',
        'gpu_capacity': 'Antec does not have enough free GPU memory. Check its other workload, then retry.',
        'host_capacity': 'Antec does not have enough free system memory. Close unneeded work on Antec, then reconnect.',
        'model_load_failed': 'The engine could not load its model. Check the engine setup and reconnect.',
        'device_mismatch': 'The engine is using a different device than configured. Check the engine setup.',
        'sampling_failed': 'An observation could not finish. Open Diagnostics for recent results; restart VOP if this persists.',
        'capture_open_failed': 'The camera could not connect. Check its power and saved address, then retry.',
        'capture_timeout': 'The camera did not respond. Check its power and network connection, then retry.',
        'overloaded': 'An observation is already running. Wait a moment, then retry.',
        'recovery_busy': 'VOP is already connecting to Antec. Wait a moment, then retry.',
        'worker_reconnect_failed': 'VOP could not reconnect to Antec. Check that it is awake and on the network, then retry.',
        'antec_name_unresolved': 'This computer cannot find Antec on the network. Check that Antec is on and connected, then select Reconnect engine in Diagnostics.',
        'ssh_missing': 'SSH is not installed on this computer. Install OpenSSH or Git for Windows, then reopen VOP.',
        'worker_identity': 'The connected worker does not match the saved model. Check advanced connection settings.',
        'clock_skew': 'The computer clocks do not agree. Synchronise Windows and Antec time, then retry.',
    }.get(code, 'VOP could not complete this operation. Retry, or open connection settings for help.')
