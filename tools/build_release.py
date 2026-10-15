"""Build a wheel and portable development installer from allow-listed repository files."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / "dist"
    out.mkdir(exist_ok=True)
    import tomllib
    version = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    with tempfile.TemporaryDirectory(prefix="vop-release-build-") as folder:
        stage = Path(folder)
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--wheel-dir", str(stage), str(root)], check=True)
        wheel = next(stage.glob("*.whl"))
        paths = ["requirements-offline.txt", "README.md", "Start VOP.cmd", "SRS-v0.2.md", "CODEX_PHASE_3.md", "CODEX_PHASE_4_PLAN.md", "CHANGELOG.md", "sample-config/phase1.json", "fixtures/scene.png",
                 "tools/run_dashboard.py", "tools/run_worker.py", "tools/process_cleanup.py", "tools/restart_smoke.py", "tools/release.py", "tools/dependency_audit.py", "tools/phase1_smoke.py", "tools/phase2_smoke.py", "tools/phase3_smoke.py", "tools/phase4_smoke.py", "install/windows.ps1", "install/README.md"]
        archive = out / f"vop-{version}-windows-dev.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(wheel, wheel.name)
            manifest = {wheel.name: sha256(wheel.read_bytes()).hexdigest()}
            for name in paths:
                bundle.write(root / name, name)
                manifest[name] = sha256((root / name).read_bytes()).hexdigest()
            bundle.writestr("manifest.json", json.dumps({"version": version, "files": manifest}, sort_keys=True, indent=2))
        print(json.dumps({"result": "PASS", "archive": str(archive), "sha256": sha256(archive.read_bytes()).hexdigest(), "wheel": wheel.name}))


if __name__ == "__main__":
    main()
