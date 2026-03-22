@echo off
setlocal enabledelayedexpansion

echo VSlicer Windows setup
echo =====================

REM Ensure we are in repo root (this file's directory).
cd /d "%~dp0"

REM Check for Python.
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python is not installed or not on PATH.
  echo Install Python 3.12+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

REM Check for mpv.
where mpv >nul 2>nul
if errorlevel 1 (
  echo mpv not found. Attempting install...
  set "CHOCO_EXE="
  if exist "%ChocolateyInstall%\\bin\\choco.exe" set "CHOCO_EXE=%ChocolateyInstall%\\bin\\choco.exe"
  if not defined CHOCO_EXE if exist "%ProgramData%\\chocolatey\\bin\\choco.exe" set "CHOCO_EXE=%ProgramData%\\chocolatey\\bin\\choco.exe"
  if defined CHOCO_EXE (
    "%CHOCO_EXE%" install -y mpv
  ) else (
    echo Chocolatey not found. Attempting to install Chocolatey...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    if exist "%ChocolateyInstall%\\bin\\choco.exe" (
      set "CHOCO_EXE=%ChocolateyInstall%\\bin\\choco.exe"
    ) else if exist "%ProgramData%\\chocolatey\\bin\\choco.exe" (
      set "CHOCO_EXE=%ProgramData%\\chocolatey\\bin\\choco.exe"
    )
    if defined CHOCO_EXE (
      "%CHOCO_EXE%" install -y mpv
    ) else (
    where winget >nul 2>nul
    if errorlevel 1 (
      echo ERROR: winget not found. Install mpv from https://mpv.io/installation/ or install winget.
      pause
      exit /b 1
    )
    echo Updating winget sources...
    winget source enable winget >nul 2>nul
    winget source update >nul 2>nul
    winget install -e --id mpv.mpv --source winget --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
      winget install -e --id mpv --source winget --accept-package-agreements --accept-source-agreements
    )
    if errorlevel 1 (
      winget install -e --name mpv --source winget --accept-package-agreements --accept-source-agreements
    )
    if errorlevel 1 (
      winget install -e --moniker mpv --source winget --accept-package-agreements --accept-source-agreements
    )
    if errorlevel 1 (
      winget install -e --id 9P3JFR0CLLL6 --source msstore --accept-package-agreements --accept-source-agreements
    )
    )
  )
)

REM Check for ffmpeg.
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ffmpeg not found. Attempting install...
  if exist "%ProgramData%\\chocolatey\\bin\\choco.exe" (
    choco install -y ffmpeg
  ) else (
    where winget >nul 2>nul
    if errorlevel 1 (
      echo ERROR: winget not found. Install ffmpeg from https://ffmpeg.org/download.html or install winget.
      pause
      exit /b 1
    )
    winget install -e --id Gyan.FFmpeg
  )
)

REM Check for yt-dlp (optional, for YouTube URLs).
where yt-dlp >nul 2>nul
if errorlevel 1 (
  echo yt-dlp not found. Attempting install...
  if exist "%ProgramData%\\chocolatey\\bin\\choco.exe" (
    choco install -y yt-dlp
  ) else (
    where winget >nul 2>nul
    if errorlevel 1 (
      echo ERROR: winget not found. Install yt-dlp from https://github.com/yt-dlp/yt-dlp or install winget.
      pause
      exit /b 1
    )
    winget install -e --id yt-dlp.yt-dlp
  )
)

REM Re-check mpv/ffmpeg after attempted install.
set "MPV_DIR="
for %%P in ("%ProgramFiles%\mpv.net" "%ProgramFiles(x86)%\mpv.net" "%ProgramFiles%\mpv" "%ProgramFiles(x86)%\mpv" "%LocalAppData%\mpv" "%LocalAppData%\Programs\mpv") do (
  if exist "%%~P\mpv.exe" set "MPV_DIR=%%~P"
)
if defined MPV_DIR (
  set "PATH=%MPV_DIR%;%PATH%"
)
where mpv >nul 2>nul
if errorlevel 1 (
  echo ERROR: mpv not found on PATH after install attempt.
  echo Install mpv from https://mpv.io/installation/ or via winget/choco.
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ERROR: ffmpeg not found on PATH after install attempt.
  echo Install ffmpeg from https://ffmpeg.org/download.html or via winget/choco.
  pause
  exit /b 1
)

REM Create venv if missing.
if not exist ".venv\\Scripts\\python.exe" (
  echo Creating .venv...
  python -m venv .venv
)

set VENV_PY=.venv\Scripts\python.exe

echo Installing Python dependencies...
"%VENV_PY%" -m pip install -e . >nul

"%VENV_PY%" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo Installing PySide6...
  "%VENV_PY%" -m pip install PySide6
)

"%VENV_PY%" -c "import pyperclip" >nul 2>nul
if errorlevel 1 (
  echo Installing pyperclip...
  "%VENV_PY%" -m pip install pyperclip
)

echo.
echo Setup complete. Double-click windows_gui.bat to launch VSlicer.
pause
endlocal
