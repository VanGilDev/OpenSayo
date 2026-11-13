@echo off
setlocal
cd /d "%~dp0"
echo Building OpenSayo v1.15 with Python 3.12...
where py >nul 2>nul
if errorlevel 1 (echo Python Launcher not found. & pause & exit /b 1)
py -3.12 -m pip install pyinstaller hidapi pillow
if errorlevel 1 (echo Dependency install failed. & pause & exit /b 1)
py -3.12 -m PyInstaller --noconfirm --clean OpenSayo.spec
if errorlevel 1 (echo Windows EXE build FAILED. & pause & exit /b 1)
echo.
echo Built successfully: dist\OpenSayo\OpenSayo.exe
echo Open the EXE from inside the whole dist folder.
pause
