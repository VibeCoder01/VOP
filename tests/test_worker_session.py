import io
import os
from pathlib import Path
import shutil
import socket
import subprocess

import pytest

from vop.contracts import ProviderError
from vop.worker_session import WorkerSession, session_script


def test_remembered_operator_key_reuses_existing_and_refuses_unreadable_file(tmp_path):
    from tools.run_dashboard import remembered_key
    class Vault:
        root = tmp_path
        value = None
        def get(self, name):
            if self.value is None: raise ProviderError("secret_unavailable", "No readable value")
            return self.value
        def set(self, name, value): self.value = value
    vault = Vault()
    assert remembered_key(vault, "first-key") == "first-key"
    assert remembered_key(vault, "second-key") == "first-key"
    vault.value = None
    (tmp_path / "dashboard-access-key.dpapi").write_bytes(b"unreadable")
    with pytest.raises(ProviderError):
        remembered_key(vault, "must-not-overwrite")
    assert vault.value is None


def test_busy_tunnel_is_never_taken_over(monkeypatch):
    class Listener:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): raise OSError("in use")
    monkeypatch.setattr(shutil, "which", lambda _: "/trusted/ssh")
    monkeypatch.setattr(socket, "socket", Listener)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: pytest.fail("Must not spawn SSH while another listener owns this port"))
    with pytest.raises(ProviderError, match="tunnel_in_use"):
        WorkerSession().start(15)


@pytest.mark.parametrize("minutes", [0, 14, 120, True, "15"])
def test_session_duration_is_bounded(minutes):
    with pytest.raises(ValueError):
        session_script(minutes)


def test_session_owns_one_tunnel_and_stops_via_stdin(monkeypatch):
    monkeypatch.setattr('vop.worker_session.antec_target', lambda: ('antec.local', []))
    commands = []
    class Process:
        def __init__(self): self.stdin = io.BytesIO(); self.exit = None; self.stopped = False
        def poll(self): return self.exit
        def wait(self, timeout): self.stopped = True; self.exit = 0; return 0
    process = Process()
    monkeypatch.setattr(shutil, "which", lambda _: "/trusted/ssh")
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kwargs: (commands.append(cmd), process)[1])
    class Listener:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def bind(self, address): pass
    monkeypatch.setattr(socket, "socket", Listener)
    session = WorkerSession()
    session.start(15)
    assert session.status()["active"]
    assert "StrictHostKeyChecking=yes" in commands[0]
    assert "127.0.0.1:8878:127.0.0.1:8878" in commands[0]
    with pytest.raises(ProviderError, match="session_active"):
        session.start(15)
    session.stop()
    assert process.stopped and not session.status()["active"]


@pytest.mark.skipif(os.name == "nt", reason="The remote helper executes on Linux; Windows session client is tested separately")
@pytest.mark.parametrize("control", ["stop\n", "", "timeout", "locked"])
def test_remote_script_restores_previous_service_with_offline_commands(tmp_path, control):
    # Execute the actual helper with fake services and a harmless sleep process; no SSH/GPU/model.
    root = tmp_path / ".local/share/vop/phase4"
    (root / "venv/bin").mkdir(parents=True)
    (root / "worker.token").write_text("offline-placeholder")
    (root / "venv/bin/python").write_text("#!/bin/sh\nexit 0\n")
    (root / "venv/bin/python").chmod(0o700)
    commands = tmp_path / "commands"
    commands.mkdir()
    systemctl = commands / "systemctl"
    systemctl.write_text('#!/bin/sh\nif [ "$2" = is-active ]; then echo active; else echo "$2" >> "$HOME/lifecycle"; fi\n')
    systemctl.chmod(0o700)
    ss = commands / "ss"
    ss.write_text("#!/bin/sh\nexit 0\n")
    ss.chmod(0o700)
    env = {**os.environ, "HOME": str(tmp_path), "PATH": str(commands) + os.pathsep + os.environ["PATH"]}
    if control == "locked":
        import fcntl
        with (root / "session.lock").open("w") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = subprocess.run(["bash", "-c", session_script(15)], input="stop\n", text=True, env=env, capture_output=True, timeout=20)
            assert result.returncode != 0
        assert not (tmp_path / "lifecycle").exists()
        return
    if control == "timeout":
        script = session_script(15).replace("read -r -t 900", "read -r -t 0.2")
        process = subprocess.Popen(["bash", "-c", script], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        try:
            assert process.wait(timeout=20) == 0
        finally:
            process.stdin.close()
            process.stderr.close()
            if process.poll() is None: process.kill(); process.wait(timeout=5)
    else:
        result = subprocess.run(["bash", "-c", session_script(15)], input=control, text=True, env=env, capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
    assert (tmp_path / "lifecycle").read_text().splitlines() == ["stop", "start"]
