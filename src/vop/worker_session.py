"""Explicit, bounded sessions for the verified antec pilot; no autostart or image capture."""
from datetime import timedelta
import os
import shlex
import shutil
import socket
import subprocess
from threading import Lock

from vop.contracts import ProviderError, utcnow


def session_script(minutes):
    if type(minutes) is not int or minutes not in (15, 30, 60):
        raise ValueError("Choose a 15, 30 or 60 minute session")
    return r'''
set -eu
vop_root="$HOME/.local/share/vop/phase4"
test -f "$vop_root/worker.token"
test -x "$vop_root/venv/bin/python"
command -v setsid >/dev/null
exec 9>"$vop_root/session.lock"
flock -n 9 || exit 1
if [ -n "$(ss -ltnH 'sport = :8878')" ]; then exit 1; fi
vop_original=$(systemctl --user is-active llama-mtp.service || true)
case "$vop_original" in active|inactive) ;; *) exit 1 ;; esac
vop_pid=''
vop_cleanup() {
    trap - EXIT HUP INT TERM
    if [ -n "$vop_pid" ]; then
        kill -TERM -- "-$vop_pid" 2>/dev/null || true
        for vop_i in {1..10}; do
            kill -0 "$vop_pid" 2>/dev/null || break
            sleep 1
        done
        kill -KILL -- "-$vop_pid" 2>/dev/null || true
        wait "$vop_pid" 2>/dev/null || true
    fi
    if [ "$vop_original" = active ]; then systemctl --user start llama-mtp.service; fi
}
trap vop_cleanup EXIT
trap 'exit 0' HUP INT TERM
if [ "$vop_original" = active ]; then systemctl --user stop llama-mtp.service; fi
setsid env PYTHONPATH="$vop_root/source/src" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$vop_root/venv/bin/python" "$vop_root/source/tools/run_worker.py" --worker-id antec-d1 --port 8878 --token-file "$vop_root/worker.token" --device cuda:0 --precision bfloat16 --cache-dir "$vop_root/model-cache" --allow-model-download --accept-model-risk > "$vop_root/worker-session.log" 2>&1 &
vop_pid=$!
read -r -t SECONDS_LIMIT vop_control || true
'''.replace("SECONDS_LIMIT", str(minutes * 60))


class WorkerSession:
    def __init__(self):
        self.process = None
        self.expires_at = None
        self.lock = Lock()

    def status(self):
        active = self.process is not None and self.process.poll() is None
        return {"active": active, "expires_at": self.expires_at if active else None,
                "ended": self.process is not None and not active}

    def start(self, minutes):
        script = session_script(minutes)
        with self.lock:
            if self.status()["active"]:
                raise ProviderError("session_active", "An antec session is already running")
            if self.process and self.process.stdin and not self.process.stdin.closed:
                self.process.stdin.close()
            ssh = shutil.which("ssh.exe" if os.name == "nt" else "ssh")
            if not ssh:
                raise ProviderError("ssh_missing", "Install OpenSSH or Git for Windows to start an antec session")
            try:
                with socket.socket() as listener:
                    listener.bind(("127.0.0.1", 8878))
            except OSError:
                raise ProviderError("tunnel_in_use", "Port 8878 is already in use. Test the existing worker connection before starting another session") from None
            command = [ssh, "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                       "-o", "ConnectTimeout=5", "-o", "ExitOnForwardFailure=yes", "-o", "ServerAliveInterval=10",
                       "-o", "ServerAliveCountMax=3", "-L", "127.0.0.1:8878:127.0.0.1:8878",
                       "antec.local", "bash -c " + shlex.quote(script)]
            try:
                self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            except OSError:
                raise ProviderError("session_start_failed", "The SSH client could not start. Check the installed SSH client and trusted antec login") from None
            self.expires_at = utcnow() + timedelta(minutes=minutes)

    def stop(self):
        with self.lock:
            if not self.status()["active"]:
                return
            try:
                self.process.stdin.write(b"stop\n")
                self.process.stdin.flush()
                self.process.stdin.close()
                self.process.wait(timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                self.process.terminate()
                self.process.wait(timeout=5)
            finally:
                if self.process.stdin and not self.process.stdin.closed:
                    self.process.stdin.close()
