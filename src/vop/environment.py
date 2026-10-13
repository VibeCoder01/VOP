"""Lightweight inventory; never imports Torch or contacts a model host."""
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys

import psutil


def versions() -> dict:
    found = {}
    for name in ("Pillow", "psutil", "pytest", "torch", "torchvision", "transformers", "huggingface-hub"):
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            found[name] = None
    return found


def inventory(disk_path: str | Path = ".") -> dict:
    mem = psutil.virtual_memory()
    hardware = {"cpu": platform.processor(), "manufacturer": None, "model": None,
                "video_controllers": None}
    if sys.platform.startswith("linux"):
        try:
            hardware["cpu"] = next(line.split(":", 1)[1].strip()
                                   for line in Path("/proc/cpuinfo").read_text().splitlines()
                                   if line.startswith("model name"))
        except (OSError, StopIteration):
            pass
    if sys.platform == "win32":
        # Local read-only CIM inventory, with no hostnames, serial numbers or private URLs.
        script = "$c=Get-CimInstance Win32_ComputerSystem; $p=Get-CimInstance Win32_Processor; " \
                 "@{cpu=($p.Name -join ', '); manufacturer=$c.Manufacturer; model=$c.Model; " \
                 "video_controllers=@(Get-CimInstance Win32_VideoController | ForEach-Object {$_.Name}); " \
                 "windows_caption=(Get-CimInstance Win32_OperatingSystem).Caption} | ConvertTo-Json -Compress"
        try:
            proc = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                  capture_output=True, text=True, timeout=15, check=True)
            hardware.update(json.loads(proc.stdout))
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            hardware["inventory_error"] = type(exc).__name__
    target = Path(disk_path).resolve()
    while not target.exists():
        target = target.parent
    return {"os": hardware.pop("windows_caption", None) or platform.platform(),
            "windows_build": platform.version() if sys.platform == "win32" else None,
            "python": platform.python_version(), "architecture": platform.machine(), "hardware": hardware,
            "total_physical_bytes": mem.total, "available_physical_bytes": mem.available,
            "free_disk_bytes": shutil.disk_usage(target).free, "dependencies": versions(),
            "accelerator_runtime_probe": "not_run; CPU benchmark; controllers are inventory only"}
