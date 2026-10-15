import os
from pathlib import Path

import pytest

from vop.contracts import ProviderError
from vop.secrets import SecretStore


def test_redirected_legacy_location_uses_newest_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    local = tmp_path / 'AppData/Local'
    monkeypatch.setenv('LOCALAPPDATA', str(local))
    vault = SecretStore(tmp_path / 'canonical')
    old = local / 'VOP/secrets/example.dpapi'
    redirected = local / 'Packages/OpenAI.Codex_fixture/LocalCache/Local/VOP/secrets/example.dpapi'
    for path in (old, redirected):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'encrypted fixture')
    os.utime(old, ns=(1000000000, 1000000000))
    os.utime(redirected, ns=(2000000000, 2000000000))
    assert vault._legacy_path('example') == redirected


def test_migration_publish_never_replaces_a_concurrent_saved_value(tmp_path):
    vault = SecretStore(tmp_path)
    target = tmp_path / 'example.dpapi'
    vault._write_blob(target, b'newly saved encrypted fixture')
    vault._write_blob(target, b'older encrypted migration fixture', replace=False)
    assert target.read_bytes() == b'newly saved encrypted fixture'
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI and MSIX vault migration')
def test_windows_migrates_redirected_dpapi_and_keeps_canonical_authoritative(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'AppData/Local'))
    monkeypatch.delenv('VOP_SECRET_DIR', raising=False)
    legacy = SecretStore(tmp_path / 'AppData/Local/Packages/OpenAI.Codex_fixture/LocalCache/Local/VOP/secrets')
    legacy.set('camera-endpoint', 'fixture-only-no-camera')
    blob = (legacy.root / 'camera-endpoint.dpapi').read_bytes()
    canonical = SecretStore()
    assert canonical.root == tmp_path / '.vop/secrets'
    assert canonical.get('camera-endpoint') == 'fixture-only-no-camera'
    assert (canonical.root / 'camera-endpoint.dpapi').read_bytes() == blob
    assert (legacy.root / 'camera-endpoint.dpapi').exists()
    canonical.set('camera-endpoint', 'corrected-fixture')
    legacy.set('camera-endpoint', 'stale-fixture')
    assert SecretStore().get('camera-endpoint') == 'corrected-fixture'


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI migration failure semantics')
def test_corrupt_legacy_value_is_preserved_and_not_migrated(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'AppData/Local'))
    monkeypatch.delenv('VOP_SECRET_DIR', raising=False)
    legacy = tmp_path / 'AppData/Local/VOP/secrets/example.dpapi'
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'invalid disposable encrypted fixture')
    vault = SecretStore()
    with pytest.raises(ProviderError):
        vault.get('example')
    assert legacy.exists() and not (vault.root / 'example.dpapi').exists()


def test_explicit_vault_is_isolated_from_legacy_storage(tmp_path, monkeypatch):
    monkeypatch.setenv('VOP_SECRET_DIR', str(tmp_path))
    vault = SecretStore()
    assert vault.root == tmp_path and not vault.migrate_legacy


@pytest.mark.skipif(os.name != 'nt', reason='Windows shared vault root')
def test_default_vault_does_not_change_with_packaged_appdata(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('VOP_SECRET_DIR', raising=False)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'AppData/Local'))
    first = SecretStore().root
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'AppData/Local/Packages/OpenAI.Codex_fixture/LocalCache/Local'))
    assert SecretStore().root == first == tmp_path / '.vop/secrets'
