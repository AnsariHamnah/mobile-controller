@echo off
setlocal EnableDelayedExpansion
:: ═══════════════════════════════════════════════════════════════════
::  Cloud Controller — One-click Installer (Xbox 360 Edition)
::  ─────────────────────────────────────────────────────────────────
::  What this does:
::    1. Checks Python 3.8+ is installed
::    2. Checks ViGEmBus driver is present
::    3. Installs all Python dependencies
::    4. Builds CloudController_Xbox.exe
::    5. Opens the dist\ folder when done
::
::  Run this INSIDE your Windows VM if you are on Mac.
:: ═══════════════════════════════════════════════════════════════════

title Cloud Controller — Xbox Installer

cls
echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   Cloud Controller — Xbox 360 Installer         ║
echo  ║   Windows only  •  ~60 seconds                  ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  ⚠  This builds the Xbox controller emulation client.
echo  ⚠  Requires ViGEmBus driver (see Step 2 below).
echo.


:: ── Step 1: Check Python ──────────────────────────────────────────────────────
echo  [1/5]  Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ❌  Python was not found.
  echo  Download from:  https://www.python.org/downloads/
  echo  Tick "Add Python to PATH" during install.
  echo.
  pause & exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo      Python %PYVER%  ✓
echo.


:: ── Step 2: Check ViGEmBus ───────────────────────────────────────────────────
echo  [2/5]  Checking ViGEmBus driver...
python -c "import vgamepad; vgamepad.VX360Gamepad()" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ────────────────────────────────────────────────────
  echo  ⚠  ViGEmBus driver not detected.
  echo.
  echo  ViGEmBus is a free, open-source Windows driver that
  echo  creates a virtual Xbox 360 controller.
  echo.
  echo  Install it now:
  echo    1. Go to:
  echo       https://github.com/nefarius/ViGEmBus/releases/latest
  echo    2. Download:  ViGEmBus_Setup_x64.exe
  echo    3. Run the installer
  echo    4. Reboot Windows
  echo    5. Run install_xbox.bat again
  echo  ────────────────────────────────────────────────────
  echo.
  echo  Opening the ViGEmBus download page...
  start "" "https://github.com/nefarius/ViGEmBus/releases/latest"
  echo.
  pause & exit /b 1
)
echo      ViGEmBus  ✓
echo.


:: ── Step 3: Upgrade pip ──────────────────────────────────────────────────────
echo  [3/5]  Upgrading pip...
python -m pip install --upgrade pip --quiet
echo      pip ready  ✓
echo.


:: ── Step 4: Install dependencies ────────────────────────────────────────────
echo  [4/5]  Installing dependencies...
echo         (websockets, vgamepad, qrcode, pyinstaller)
echo.

python -m pip install websockets vgamepad qrcode pyinstaller --quiet
if errorlevel 1 (
  echo.
  echo  ❌  Dependency installation failed.
  echo  Try:  pip install websockets vgamepad qrcode pyinstaller
  echo.
  pause & exit /b 1
)
echo      All dependencies installed  ✓
echo.


:: ── Step 5: Build ────────────────────────────────────────────────────────────
echo  [5/5]  Building CloudController_Xbox.exe ...
echo         (About 30-45 seconds)
echo.

pyinstaller ^
  --onefile ^
  --console ^
  --name "CloudController_Xbox" ^
  --hidden-import "vgamepad.win.vigem_client" ^
  --hidden-import "vgamepad.win.vigem_commons" ^
  --hidden-import "vgamepad.win.vigem_target" ^
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
  client_xbox.py > build_temp\build_log_xbox.txt 2>&1

echo.
if exist "dist\CloudController_Xbox.exe" (
  echo  ╔══════════════════════════════════════════════════╗
  echo  ║   ✅  Build successful!                          ║
  echo  ║                                                  ║
  echo  ║   dist\CloudController_Xbox.exe                  ║
  echo  ║                                                  ║
  echo  ║   How to use:                                    ║
  echo  ║   1. Double-click CloudController_Xbox.exe       ║
  echo  ║   2. Scan QR on your phone                       ║
  echo  ║   3. Tap PRESS START                             ║
  echo  ║   4. Phone is now a real Xbox controller         ║
  echo  ║                                                  ║
  echo  ║   Mac users: run this .exe inside Windows VM     ║
  echo  ╚══════════════════════════════════════════════════╝
  echo.
  start "" "dist"
) else (
  echo  ╔══════════════════════════════════════════════════╗
  echo  ║   ❌  Build failed.                              ║
  echo  ║   See build_temp\build_log_xbox.txt              ║
  echo  ╚══════════════════════════════════════════════════╝
  echo.
  start "" "build_temp"
)

echo.
pause