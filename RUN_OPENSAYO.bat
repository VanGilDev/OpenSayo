@echo off
setlocal
cd /d "%~dp0"
echo OpenSayo v1.15 - run from source (Windows)
where py >nul 2>nul
if errorlevel 1 (
  echo Python Launcher not found. Install Python 3.12 and enable the py launcher.
  pause
  exit /b 1
)
py -3.12 --version >nul 2>nul
if errorlevel 1 (
  echo Python 3.12 not found. This version targets Python 3.12.
  pause
  exit /b 1
)
py -3.12 "py\opensayo_v019_alpha22.py"
if errorlevel 1 (
  echo.
  echo The program stopped or encountered an error. Capture the message above.
  pause
)
endlocal
