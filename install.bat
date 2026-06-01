@echo off
setlocal EnableDelayedExpansion
:: ═══════════════════════════════════════════════════════════════════
::  Cloud Controller — One-click Installer + Builder
::  ─────────────────────────────────────────────────────────────────
::  What this does:
::    1. Checks Python 3.8+ is installed
::    2. Installs all Python dependencies
::    3. Installs PyInstaller
::    4. Builds CloudController.exe
::    5. Opens the dist\ folder when done
::
::  Requirements:
::    • Python 3.8 or newer installed from python.org
::      (make sure "Add Python to PATH" was ticked during install)
::
::  Usage:
::    Double-click this file.
::    After it finishes, find CloudController.exe in the dist\ folder.
:: ═══════════════════════════════════════════════════════════════════

title Cloud Controller — Installer

cls
echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   Cloud Controller — Installer               ║
echo  ║   This will take about 60 seconds            ║
echo  ╚══════════════════════════════════════════════╝
echo.


:: ── Step 1: Check Python is available ────────────────────────────────────────
echo  [1/4]  Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ❌  Python was not found.
  echo.
  echo  Please install Python 3.8 or newer from:
  echo  https://www.python.org/downloads/
  echo.
  echo  IMPORTANT: Tick "Add Python to PATH" during installation.
  echo.
  pause
  exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo      Found Python %PYVER%  ✓
echo.


:: ── Step 2: Upgrade pip silently ─────────────────────────────────────────────
echo  [2/4]  Upgrading pip...
python -m pip install --upgrade pip --quiet
if errorlevel 1 (
  echo      pip upgrade failed — continuing anyway
)
echo      pip ready  ✓
echo.


:: ── Step 3: Install dependencies ─────────────────────────────────────────────
echo  [3/4]  Installing dependencies...
echo         (websockets, pynput, qrcode, pyinstaller)
echo.

python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
  echo.
  echo  ❌  Dependency installation failed.
  echo  Try running this command manually:
  echo      pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

python -m pip install pyinstaller --quiet
if errorlevel 1 (
  echo.
  echo  ❌  PyInstaller installation failed.
  echo  Try running:  pip install pyinstaller
  echo.
  pause
  exit /b 1
)

echo      All dependencies installed  ✓
echo.


:: ── Step 4: Build the exe ─────────────────────────────────────────────────────
echo  [4/4]  Building CloudController.exe ...
echo         (This is the slowest step — about 30-45 seconds)
echo.

pyinstaller ^
  --onefile ^
  --console ^
  --name "CloudController" ^
  --hidden-import "pynput.keyboard._win32" ^
  --hidden-import "pynput.mouse._win32" ^
  --hidden-import "pynput.keyboard._darwin" ^
  --hidden-import "pynput.mouse._darwin" ^
  --hidden-import "pynput.keyboard._xorg" ^
  --hidden-import "pynput.mouse._xorg" ^
  --hidden-import "qrcode.image.base" ^
  --hidden-import "qrcode.image.pure" ^
  --hidden-import "qrcode.image.svg" ^
  --hidden-import "websockets.legacy.client" ^
  --hidden-import "websockets.legacy.server" ^
  --hidden-import "websockets.connection" ^
  --hidden-import "websockets.exceptions" ^
  --distpath "dist" ^
  --workpath "build_temp" ^
  --specpath "build_temp" ^
  --noconfirm ^
  client.py > build_temp\build_log.txt 2>&1

:: ── Result ────────────────────────────────────────────────────────────────────
echo.
if exist "dist\CloudController.exe" (
  echo  ╔══════════════════════════════════════════════╗
  echo  ║   ✅  Build successful!                      ║
  echo  ║                                              ║
  echo  ║   Your file:                                 ║
  echo  ║   dist\CloudController.exe                   ║
  echo  ║                                              ║
  echo  ║   Share this single .exe with anyone.        ║
  echo  ║   They just double-click it — no Python.     ║
  echo  ╚══════════════════════════════════════════════╝
  echo.
  echo  Opening dist\ folder...
  start "" "dist"
) else (
  echo  ╔══════════════════════════════════════════════╗
  echo  ║   ❌  Build failed.                          ║
  echo  ║   See build_temp\build_log.txt for details.  ║
  echo  ╚══════════════════════════════════════════════╝
  echo.
  echo  Common fixes:
  echo    • Run as Administrator
  echo    • Temporarily disable antivirus
  echo    • Delete the build_temp\ folder and try again
  echo.
  start "" "build_temp"
)

echo.
pause