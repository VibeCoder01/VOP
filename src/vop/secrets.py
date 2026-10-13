"""Local secret references. Windows DPAPI binds encrypted values to the signed-in user."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess

from vop.contracts import ProviderError

REF = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def reference(value):
    if not isinstance(value, str) or not REF.fullmatch(value):
        raise ValueError("Secret reference must be 1–64 letters, digits, dots, underscores or hyphens")
    return value


class SecretStore:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "VOP" / "secrets"

    def _crypt(self, data, decrypt=False):
        class Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]
        buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
        source, target = Blob(len(data), buffer), Blob()
        function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
        function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        function.restype = wintypes.BOOL
        if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
            raise ProviderError("secret_unavailable", "OS secret protection could not open this value")
        try:
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(ctypes.cast(target.pbData, ctypes.c_void_p))

    def set(self, name, value):
        name = reference(name)
        if not isinstance(value, str) or not value or len(value.encode()) > 8192:
            raise ValueError("Secret must contain 1–8192 UTF-8 bytes")
        if os.name == "nt":
            self.root.mkdir(parents=True, exist_ok=True)
            path = self.root / (name + ".dpapi")
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(self._crypt(value.encode()))
            temporary.replace(path)
        else:
            try:
                subprocess.run(["secret-tool", "store", "--label=VOP " + name, "application", "vop", "reference", name], input=value.encode(), check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                raise ProviderError("secret_store_unavailable", "An unlocked OS Secret Service is required") from None

    def get(self, name):
        name = reference(name)
        try:
            if os.name == "nt":
                return self._crypt((self.root / (name + ".dpapi")).read_bytes(), True).decode()
            result = subprocess.run(["secret-tool", "lookup", "application", "vop", "reference", name], check=True, timeout=10, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            if not result.stdout.strip():
                raise OSError()
            return result.stdout.decode().rstrip("\n")
        except (OSError, UnicodeError, subprocess.SubprocessError):
            raise ProviderError("secret_unavailable", "Supply this secret through local protected setup") from None

    def camera(self, name):
        try:
            value = json.loads(self.get(name))
            if set(value) != {"username", "password"} or any(not isinstance(v, str) or not 1 <= len(v) <= 128 or any(ord(c) < 32 for c in v) for v in value.values()):
                raise ValueError()
            return value
        except (ValueError, TypeError):
            raise ProviderError("secret_unavailable", "Camera secret has an invalid format") from None
