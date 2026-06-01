@echo off
:: ═══════════════════════════════════════════════════════════════════
::  Cloud Controller — Build Script (Xbox 360 Emulation Edition)
::  Produces:  dist\CloudController_Xbox.exe
::
::  Requirements (run once):
::      pip install pyinstaller websockets vgamepad qrcode
::
::  Also requires ViGEmBus driver on the TARGET machine:
::      https://github.com/nefarius/ViGEmBus/releases/latest
:: ═══════════════════════════════════════════════════════════════════

title Cloud Controller — Building Xbox client
echo.
echo  Building CloudController_Xbox.exe ...
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
  client_xbox.py

echo.
if exist "dist\CloudController_Xbox.exe" (
  echo  ✅  Build successful.
  echo  Output:  dist\CloudController_Xbox.exe
  echo.
  echo  Remember: ViGEmBus must be installed on the machine
  echo  that runs this .exe, and it must be Windows.
  echo  Mac users: run the .exe INSIDE the Windows VM.
) else (
  echo  ❌  Build failed.  Check output above for errors.
)
echo.
pause