@echo off
setlocal

REM Ensure we are in repo root (this file's directory).
cd /d "%~dp0"

REM Use venv if available, otherwise fall back to system Python.
if exist ".venv\Scripts\pythonw.exe" (
  set "VENV_PY=.venv\Scripts\pythonw.exe"
) else (
  set "VENV_PY=pythonw"
)

set PYTHONPATH=src
start "" "%VENV_PY%" -m vslicer_gui.app

endlocal
