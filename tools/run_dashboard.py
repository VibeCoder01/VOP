"""Convenience local launcher. Generates a session key unless one is already set."""
import os
from pathlib import Path
import secrets
import sys
import argparse
import socket
from threading import Timer
import webbrowser
import http.client
import json
import time
import psutil

import uvicorn

from vop.config import load_config
from vop.service import create_app


def remembered_key(vault, candidate):
    from vop.contracts import ProviderError
    try:
        return vault.get("dashboard-access-key")
    except ProviderError:
        if (vault.root / "dashboard-access-key.dpapi").exists():
            raise  # A decryption failure must not silently rotate the existing key.
        vault.set("dashboard-access-key", candidate)
        return candidate


def owned_dashboard(process, port):
    """Match this installation, Python runtime, Windows account and requested port."""
    try:
        if process.username() != psutil.Process().username():
            return False
        runtimes = {Path(sys.executable).resolve(), Path(sys._base_executable).resolve()}
        if Path(process.exe()).resolve() not in runtimes:
            return False
        command = process.cmdline()
        if len(command) < 2:
            return False
        script = Path(command[1])
        if not script.is_absolute(): script = Path(process.cwd()) / script
        if script.resolve() != Path(__file__).resolve():
            return False
        selected_port = 8765
        for index, argument in enumerate(command[2:], 2):
            if argument == '--port': selected_port = int(command[index + 1])
            elif argument.startswith('--port='): selected_port = int(argument.split('=', 1)[1])
        return selected_port == port
    except (psutil.Error, OSError, ValueError, IndexError):
        return False


def trusted_listener(port):
    try:
        if any(entry.status == psutil.CONN_LISTEN and entry.laddr.ip == '127.0.0.1'
                   and entry.laddr.port == port and entry.pid and owned_dashboard(psutil.Process(entry.pid), port)
                   for entry in psutil.net_connections(kind='tcp')):
            return True
        # Windows can report LISTEN with PID 0 and the owning bound socket as
        # NONE. Verify the server side of a fresh connection instead; a bound
        # socket alone is not evidence that its process accepted this connection.
        with socket.create_connection(('127.0.0.1', port), timeout=.5) as probe:
            peer = probe.getsockname()
            return any(entry.status == psutil.CONN_ESTABLISHED
                       and entry.laddr == ('127.0.0.1', port) and entry.raddr == peer
                       and entry.pid and owned_dashboard(psutil.Process(entry.pid), port)
                       for entry in psutil.net_connections(kind='tcp'))
    except (psutil.Error, OSError):
        return False


def wait_for_exit(processes, seconds):
    deadline = time.monotonic() + seconds
    while True:
        alive = []
        for process in processes:
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    alive.append(process)
            except psutil.NoSuchProcess:
                pass
        if not alive or time.monotonic() >= deadline:
            return
        time.sleep(.1)


def stop_existing(port, token, *, graceful_seconds=90):
    ancestors = {os.getpid(), *(parent.pid for parent in psutil.Process().parents())}
    targets = [process for process in psutil.process_iter() if process.pid not in ancestors and owned_dashboard(process, port)]
    if trusted_listener(port):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=35)
        try:
            connection.request('POST', '/api/v1/shutdown', headers={'Authorization': 'Bearer ' + token})
            response = connection.getresponse()
            response.read(4096)
            graceful = response.status == 202
            if not graceful:
                # Older VOP versions have no lifecycle endpoint; close their owned session first.
                connection.request('POST', '/integration/session/stop', headers={'Authorization': 'Bearer ' + token})
                connection.getresponse().read(4096)
        except (OSError, http.client.HTTPException):
            graceful = False
        finally:
            connection.close()
        if graceful:
            # Linux zombies have exited; only their original parent can reap them.
            wait_for_exit(targets, graceful_seconds)
    for process in targets:
        if not process.is_running() or not owned_dashboard(process, port):
            continue
        try:
            descendants = process.children(recursive=True)
            for child in [*reversed(descendants), process]:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
            _, alive = psutil.wait_procs([process, *descendants], timeout=5)
            for child in alive:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(alive, timeout=5)
        except psutil.NoSuchProcess:
            pass
    try:
        with socket.socket() as listener:
            if os.name != 'nt':
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(('127.0.0.1', port))
    except OSError:
        raise RuntimeError('The VOP port is still in use. An unrelated process was left running. Close it or choose another port.') from None


def managed_run(app, port):
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False, log_level='warning'))
    requested = []

    def shutdown(mode):
        if requested:
            return
        requested.append(mode)
        app.state.pipeline.stopping = True
        app.state.sampler.stop_event.set()
        app.state.reliable.stop_event.set()
        server.should_exit = True

    app.state.shutdown_request = shutdown
    server.run()
    return requested == ['restart']


def open_workspace(port, token):
    if not trusted_listener(port):
        raise OSError('Waiting for the owned VOP listener')
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.request('POST', '/api/v1/browser-ticket', headers={'Authorization': 'Bearer ' + token})
        response = connection.getresponse()
        body = response.read(4096)
        if response.status != 200:
            raise RuntimeError('The running app could not authenticate this launcher. Close VOP and open Start VOP again; do not change any keys.')
        path = json.loads(body)['url']
        if not path.startswith('/launch/') or '/' in path[len('/launch/'):]:
            raise RuntimeError('Unexpected launcher response')
        webbrowser.open(f'http://127.0.0.1:{port}' + path)
    finally:
        connection.close()


def open_when_ready(port, token):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            open_workspace(port, token)
            return
        except OSError:
            time.sleep(.5)
        except (RuntimeError, ValueError, KeyError):
            print('VOP could not open a signed-in workspace. Close VOP and reopen Start VOP. Your saved settings are retained.', flush=True)
            return
    print('VOP is taking longer to start. Open Start VOP again in a moment.', flush=True)


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Start the local VOP browser dashboard")
    parser.add_argument("config", nargs="?", type=Path, default=root / "sample-config" / "phase1.json")
    parser.add_argument("--allow-live-sources", action="store_true")
    parser.add_argument("--allow-remote-inference", action="store_true", help="Compatibility flag; the dashboard already uses its explicitly selected worker")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--remember-access-key", action="store_true", help="Reuse a Windows DPAPI-protected operator key")
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument('--show-access-key', action='store_true', help='Advanced: display the API/operator key for manual clients')
    parser.add_argument('--manual-worker', action='store_true', help='Disable automatic on-demand Antec recovery')
    parser.add_argument('--restart-existing', action='store_true', help='Stop this installation’s existing VOP server before starting')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be 1–65535")
    path = args.config.resolve()
    token = os.environ.get("VOP_API_TOKEN") or secrets.token_urlsafe(32)
    if (args.remember_access_key or args.open_browser and os.name == 'nt') and not os.environ.get("VOP_API_TOKEN"):
        if os.name != "nt":
            parser.error("Remembered launcher access keys currently require Windows DPAPI")
        from vop.secrets import SecretStore
        try:
            token = remembered_key(SecretStore(), token)
        except Exception:
            parser.exit(1, 'VOP could not unlock its saved Windows settings. Close VOP, sign in with the same Windows account and try Start VOP again. No keys were replaced.\n')
    settings = load_config(path)
    if args.restart_existing:
        print('Stopping previous VOP instances. Waiting for current work to finish…', flush=True)
        try:
            stop_existing(args.port, token)
        except (RuntimeError, psutil.Error) as exc:
            parser.exit(1, str(exc) + '\n')
    elif args.open_browser:
        try:
            with socket.create_connection(('127.0.0.1', args.port), timeout=.5):
                pass
        except OSError:
            pass
        else:
            try:
                open_workspace(args.port, token)
            except (OSError, RuntimeError, ValueError, KeyError):
                parser.exit(1, 'VOP is already running but could not open your workspace. Close VOP and reopen Start VOP. No key entry is needed.\n')
            return
    print(f"VOP dashboard: http://127.0.0.1:{args.port}")
    if args.show_access_key:
        print('Advanced operator/API key:')
        print(token, flush=True)
    print('Open Start VOP for automatic sign-in. Saved setup is reused; Antec connects when needed. Press Ctrl+C to stop.', flush=True)
    app = create_app(settings, token=token, allow_live_sources=args.allow_live_sources, allow_remote_inference=True, auto_recover=not args.manual_worker, live_workspace=args.allow_live_sources)
    if args.open_browser:
        opener = Timer(1, open_when_ready, args=(args.port, token))
        opener.daemon = True
        opener.start()
    if managed_run(app, args.port):
        # A new interpreter reloads code as well as configuration. Retain browser sessions.
        os.environ['VOP_API_TOKEN'] = token
        os.execv(sys.executable, [sys.executable, *(argument for argument in sys.argv if argument != '--open-browser')])


if __name__ == "__main__":
    main()
