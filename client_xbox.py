"""
PC Client — Cloud Controller  (Phase 4 · Xbox 360 Emulation)
═════════════════════════════════════════════════════════════
Creates a virtual Xbox 360 controller via ViGEmBus.
The game sees real hardware — not keyboard input.

⚠  WINDOWS ONLY.
   If you are on Mac with a Windows VM, copy this .exe
   INSIDE the VM and run it there.

Setup (one time only)
─────────────────────
  1. Install ViGEmBus driver:
     https://github.com/nefarius/ViGEmBus/releases/latest
     Download  ViGEmBus_Setup_x64.exe  → run → reboot

  2. Install Python packages:
     pip install websockets vgamepad qrcode

Usage
─────
    python client_xbox.py
    — or double-click CloudController_Xbox.exe after building

What the phone controls
───────────────────────
    Left  joystick  →  Xbox left  stick  (movement / walk)
    Right joystick  →  Xbox right stick  (camera / look)
    A button        →  Xbox A  (jump / confirm)
    B button        →  Xbox B  (cancel / crouch)
    X button        →  Xbox X  (reload / interact)
    Y button        →  Xbox Y  (special / ability)
    (Button remapping on phone is ignored in Xbox mode —
     buttons map directly to matching Xbox hardware buttons)
"""

import asyncio
import io
import json
import logging
import random
import sys

# ── ViGEmBus check ────────────────────────────────────────────────────────────
try:
    import vgamepad as vg
except ImportError:
    print()
    print("  ❌  vgamepad is not installed.")
    print("  Run:  pip install vgamepad")
    print()
    sys.exit(1)

# ── Optional QR ───────────────────────────────────────────────────────────────
try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

import websockets

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  — update both URLs before running
# ══════════════════════════════════════════════════════════════════════════════

RELAY_URL  = "wss://controller-cloud.onrender.com/"
PAGES_URL  = "https://YOUR-USERNAME.github.io/controller"   # ← update this

# ══════════════════════════════════════════════════════════════════════════════
#  ROOM CODE GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

_WORDS = [
    "TIGER",  "NOVA",   "SHADOW", "FALCON", "STORM",
    "BLAZE",  "VIPER",  "GHOST",  "APEX",   "DELTA",
    "SONIC",  "IRON",   "FROST",  "EMBER",  "SWIFT",
    "PULSE",  "OMEGA",  "RAZOR",  "FLARE",  "BOLT",
]

def generate_room_code() -> str:
    return f"{random.choice(_WORDS)}-{random.randint(10, 99)}"

# ══════════════════════════════════════════════════════════════════════════════
#  VIRTUAL GAMEPAD
# ══════════════════════════════════════════════════════════════════════════════

def create_gamepad():
    """
    Attempt to create the virtual Xbox 360 controller.
    Shows a clear error if ViGEmBus is not installed.
    """
    try:
        pad = vg.VX360Gamepad()
        log.info("✅  Virtual Xbox 360 controller created.")
        return pad
    except Exception as e:
        print()
        print("  ❌  Could not create virtual Xbox controller.")
        print()
        print("  Most likely cause: ViGEmBus driver is not installed.")
        print()
        print("  Fix:")
        print("    1. Download ViGEmBus_Setup_x64.exe from:")
        print("       https://github.com/nefarius/ViGEmBus/releases/latest")
        print("    2. Run the installer")
        print("    3. Reboot your PC")
        print("    4. Run this client again")
        print()
        print(f"  Technical detail: {e}")
        print()
        sys.exit(1)


# ── Xbox button lookup ────────────────────────────────────────────────────────
# Maps the phone's button names to vgamepad Xbox button constants.
XBOX_BUTTONS: dict = {
    "A": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
    "B": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
    "X": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
    "Y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
}

# Track which buttons are currently held to avoid redundant press/release calls
_held_buttons: set[str] = set()

# ── Axis conversion ───────────────────────────────────────────────────────────

def to_axis(value: float) -> int:
    """
    Convert phone joystick value (-1.0 … +1.0)
    to Xbox axis integer (-32768 … +32767).
    """
    clamped = max(-1.0, min(1.0, float(value)))
    return int(clamped * 32767)


def apply_state(pad: vg.VX360Gamepad, data: dict) -> None:
    """
    Translate one controller-state dict into virtual Xbox 360 inputs.

    Phone  →  Xbox
    ─────────────────────────────────────────────────────
    leftJoy.x          →  left  stick X   (strafe left/right)
    leftJoy.y          →  left  stick Y   (move  forward/back)  ← Y negated
    rightJoy.x         →  right stick X   (look  left/right)
    rightJoy.y         →  right stick Y   (look  up/down)       ← Y negated
    buttons.A          →  Xbox A
    buttons.B          →  Xbox B
    buttons.X          →  Xbox X
    buttons.Y          →  Xbox Y
    """
    # ── Left joystick ─────────────────────────────────────────────────────────
    lx = data.get("leftJoy",  {}).get("x", 0.0)
    ly = data.get("leftJoy",  {}).get("y", 0.0)

    # ── Right joystick ────────────────────────────────────────────────────────
    rx = data.get("rightJoy", {}).get("x", 0.0)
    ry = data.get("rightJoy", {}).get("y", 0.0)

    # Y is negated:
    #   phone y = -1  means stick pushed UP  → Xbox y = +32767 (forward)
    #   phone y = +1  means stick pushed DOWN → Xbox y = -32767 (backward)
    pad.left_joystick( x_value=to_axis( lx), y_value=to_axis(-ly))
    pad.right_joystick(x_value=to_axis( rx), y_value=to_axis(-ry))

    # ── ABXY buttons ──────────────────────────────────────────────────────────
    buttons = data.get("buttons", {})

    for btn_name, xbox_btn in XBOX_BUTTONS.items():
        pressed = bool(buttons.get(btn_name, False))

        if pressed and btn_name not in _held_buttons:
            pad.press_button(button=xbox_btn)
            _held_buttons.add(btn_name)

        elif not pressed and btn_name in _held_buttons:
            pad.release_button(button=xbox_btn)
            _held_buttons.discard(btn_name)

    # Send all changes to the virtual controller in one HID report
    pad.update()


def release_all(pad: vg.VX360Gamepad) -> None:
    """
    Zero every axis and release every button.
    Called on disconnect so the game doesn't see stuck inputs.
    """
    try:
        # Release all held Xbox buttons
        for btn_name in list(_held_buttons):
            xbox_btn = XBOX_BUTTONS.get(btn_name)
            if xbox_btn:
                try:   pad.release_button(button=xbox_btn)
                except Exception: pass
        _held_buttons.clear()

        # Zero joysticks and triggers
        pad.left_joystick( x_value=0, y_value=0)
        pad.right_joystick(x_value=0, y_value=0)
        pad.left_trigger(value=0)
        pad.right_trigger(value=0)
        pad.update()

    except Exception:
        pass  # gamepad may have been torn down already

# ══════════════════════════════════════════════════════════════════════════════
#  TERMINAL DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def print_header(room_code: str) -> None:
    url = f"{PAGES_URL}?room={room_code}"
    W   = 58

    print()
    print("═" * W)
    print("  🎮  CLOUD CONTROLLER  —  PC HOST  (Xbox Mode)")
    print("═" * W)
    print(f"  Room code  :  {room_code}")
    print(f"  Share URL  :  {url}")
    print("─" * W)

    if HAS_QR:
        print("  Scan this QR code with your phone:\n")
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=1, border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        for line in buf.getvalue().splitlines():
            print("  " + line)
    else:
        print("  ⚠  QR display unavailable.  pip install qrcode")
        print(f"\n  Open on phone:  {url}")

    print("─" * W)
    print("  Mode         :  Virtual Xbox 360 controller")
    print("  Left stick   :  Walk / Move")
    print("  Right stick  :  Look / Camera")
    print("  A B X Y      :  Xbox face buttons (direct)")
    print("─" * W)
    print("  ⚠  Run this INSIDE the Windows VM if on Mac")
    print("═" * W)
    print()

# ══════════════════════════════════════════════════════════════════════════════
#  WEBSOCKET CLIENT
# ══════════════════════════════════════════════════════════════════════════════

async def run(room_code: str, pad: vg.VX360Gamepad) -> None:
    backoff = 2

    while True:
        try:
            log.info(f"Connecting to relay…  ({RELAY_URL})")

            async with websockets.connect(
                RELAY_URL,
                ping_interval=20,
                ping_timeout=30,
                open_timeout=10,
            ) as ws:

                # ── Join room ─────────────────────────────────────────────────
                await ws.send(json.dumps({
                    "type": "join",
                    "room": room_code,
                    "role": "pc",
                }))

                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                msg = json.loads(raw)

                if msg.get("type") == "joined":
                    log.info(
                        f"✅  Joined room '{msg.get('room')}' as '{msg.get('role')}'"
                    )
                    print(
                        f"\n  ✅  Room '{room_code}' is live — "
                        f"Virtual Xbox controller ready.\n"
                        f"  Waiting for phone to connect…\n"
                    )
                else:
                    log.warning(f"Unexpected first message: {msg}")

                backoff = 2   # reset on clean connect

                # ── Process messages ──────────────────────────────────────────
                async for message in ws:
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        continue

                    # Config messages — sensitivity / button remap
                    # In Xbox mode sensitivity is irrelevant (sticks are direct),
                    # and button remap is ignored (A/B/X/Y map to Xbox hardware).
                    # We acknowledge silently and continue.
                    if data.get("type") == "config":
                        log.debug("Config message received (ignored in Xbox mode)")
                        continue

                    # Skip any other non-state messages
                    if "leftJoy" not in data and "rightJoy" not in data:
                        continue

                    apply_state(pad, data)

        except (websockets.ConnectionClosed,
                ConnectionRefusedError,
                OSError) as e:
            log.warning(f"Connection lost: {e}")

        except asyncio.TimeoutError:
            log.warning("Connection timed out.")

        finally:
            release_all(pad)

        log.info(f"Reconnecting in {backoff}s…")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    room_code = generate_room_code()

    # Create the virtual controller before printing the header
    # so any ViGEmBus errors surface immediately
    pad = create_gamepad()

    print_header(room_code)

    try:
        asyncio.run(run(room_code, pad))
    except KeyboardInterrupt:
        release_all(pad)
        print("\n  Controller stopped.  Virtual Xbox controller released.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()