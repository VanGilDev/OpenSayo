@echo off
setlocal
cd /d "%~dp0"
echo OpenSayo v1.15 Step41 - OFFLINE checks (no USB access)
py -3.12 Tests\offline_check.py
if errorlevel 1 (echo OFFLINE CHECK FAILED. & pause & exit /b 1)
echo OFFLINE CHECK PASSED.
pause
