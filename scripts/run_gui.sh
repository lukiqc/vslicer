#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v python >/dev/null 2>&1; then
  echo "ERROR: Python is not installed or not on PATH."
  exit 1
fi

if ! command -v mpv >/dev/null 2>&1; then
  echo "ERROR: mpv not found. Install mpv."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ERROR: ffmpeg not found. Install ffmpeg."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating .venv..."
  python -m venv .venv
fi

VENV_PY=".venv/bin/python"

$VENV_PY -m pip install -e . >/dev/null

if $VENV_PY -c "import PySide6" >/dev/null 2>&1; then
  echo "PySide6 already installed"
else
  $VENV_PY -m pip install PySide6
fi

if $VENV_PY -c "import pyperclip" >/dev/null 2>&1; then
  echo "pyperclip already installed"
else
  $VENV_PY -m pip install pyperclip
fi

export PYTHONPATH=src
exec $VENV_PY -m vslicer_gui.app
