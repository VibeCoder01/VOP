@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo VOP needs its Python environment installed first. See README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" tools\run_dashboard.py --allow-live-sources --remember-access-key --open-browser
if errorlevel 1 pause
