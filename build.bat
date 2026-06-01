@echo off
:: ═══════════════════════════════════════════════════════════════
::  Cloud Controller — Build Script (Keyboard / Mouse Edition)
::  Produces:  dist\client.exe
::
::  Requirements (run once before building):
::      pip install pyinstaller websockets pynput qrcode
::
::  Usage:
::      Double-click build.bat   OR   run from terminal
:: ═══════════════════════════════════════════════════════════════

title Cloud Controller — Building client.exe
echo.
echo  Building client.exe ...
echo  This takes about 30-60 seconds on first run.
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
  client.py

echo.
if exist "dist\CloudController.exe" (
  echo  ✅  Build successful.
  echo  Output:  dist\CloudController.exe
  echo.
  echo  Share this single file — no Python needed on the target machine.
) else (
  echo  ❌  Build failed.  Check the output above for errors.
)
echo.
pause