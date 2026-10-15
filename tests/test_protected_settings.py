"""Disposable protected values only; no user credentials or camera connections."""
import os
import subprocess
import sys

import pytest

from vop.config import SourceSpec
from vop.contracts import ProviderError
from vop.secrets import SecretStore
from vop.ui_readiness import camera_dependencies


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_protected_value_survives_new_process_and_concurrent_reads(tmp_path):
    vault = SecretStore(tmp_path)
    vault.set("generated-test", "disposable-round-trip-value")
    script = """
import sys
from concurrent.futures import ThreadPoolExecutor
from vop.secrets import SecretStore
vault = SecretStore(sys.argv[1])
with ThreadPoolExecutor(max_workers=16) as pool:
    values = list(pool.map(lambda _: vault.get('generated-test'), range(256)))
assert all(value == 'disposable-round-trip-value' for value in values)
print('PASS')
"""
    result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"


@pytest.mark.parametrize("code,expected", [("endpoint_denied", "allowed address"), ("secret_unavailable", "could not unlock")])
def test_camera_address_failure_is_distinct_from_vault_failure(monkeypatch, code, expected):
    def fail(source):
        raise ProviderError(code, "private details must not appear")
    monkeypatch.setattr("vop.ui_readiness.camera_endpoint", fail)
    source = SourceSpec("test-camera", "Test", "snapshot", {"endpoint_secret_ref": "test-endpoint"}, ())
    problems = camera_dependencies(source)
    assert len(problems) == 1 and expected in problems[0][0]
    assert "private details" not in problems[0][0]


def test_missing_protected_value_logs_category_without_value_or_reference(tmp_path, caplog):
    if os.name != "nt":
        pytest.skip("Windows file-backed DPAPI")
    with pytest.raises(ProviderError):
        SecretStore(tmp_path).get("private-reference")
    assert "FileNotFoundError" in caplog.text
    assert "private-reference" not in caplog.text and str(tmp_path) not in caplog.text
