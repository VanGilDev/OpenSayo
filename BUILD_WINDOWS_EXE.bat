@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (echo Python launcher not found. Install Python 3.12 64-bit. & pause & exit /b 1)
py -3.12 -m pip install --upgrade pyinstaller hidapi pillow
if errorlevel 1 (echo Dependency installation failed. & pause & exit /b 1)
py -3.12 -m PyInstaller --noconfirm --clean OpenSayo.spec
if errorlevel 1 (echo EXE build failed. & pause & exit /b 1)
echo.
echo Built: dist\OpenSayo\OpenSayo.exe
echo Copy the WHOLE dist\OpenSayo folder to your laptop.
pause
