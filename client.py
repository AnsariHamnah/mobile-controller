"""
PC Client — Cloud Controller  (Phase 1 · Settings-aware)
═════════════════════════════════════════════════════════
What's new vs the previous version
───────────────────────────────────
• Handles {"type":"config"} messages from the phone
  — mouseSensitivity updated live (no restart needed)
  — buttonMap updated live (key remapping takes effect immediately)
• resolve_key() maps string names like "space", "f1", "e" → pynput keys
• All other behaviour identical to Room Edition client

Dependencies
────────────
    pip install websockets pynput qrcode

Usage
─────
    python client.py
"""

import asyncio
import io
import json
import logging
import random
import sys

try:
    import qrcode
    HAS_QR = True
except ImportError:
    HAS_QR = False

import websockets
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Controller as MouseController

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  — update both URLs before running
# ══════════════════════════════════════════════════════════════════════════════

RELAY_URL = "wss://mobile-controller-relay.onrender.com"
PAGES_URL = "https://ansarihamnah.github.io/mobile-controller"

# ── Defaults (overridden live by config messages from phone) ──────────────────
MOUSE_SENSITIVITY: float = 5.0   # matches phone default slider value
DEADZONE:          float = 0.08  # phone applies dead-zone, this is a backup

# ── Default button map (overridden live by config messages from phone) ────────
# Values must match the key strings the phone sends in buttonMap
BUTTON_MAP: dict = {
    "A": Key.space,
    "B": "e",
    "X": "r",
    "Y": "f",
}

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
#  KEY RESOLVER
#  Converts the string key names the phone sends into pynput key objects.
# ══════════════════════════════════════════════════════════════════════════════

_SPECIAL_KEYS: dict = {
    "space":  Key.space,
    "enter":  Key.enter,
    "shift":  Key.shift,
    "ctrl":   Key.ctrl,
    "alt":    Key.alt,
    "tab":    Key.tab,
    "esc":    Key.esc,
    "f1":     Key.f1,  "f2":  Key.f2,  "f3":  Key.f3,
    "f4":     Key.f4,  "f5":  Key.f5,  "f6":  Key.f6,
    "f7":     Key.f7,  "f8":  Key.f8,  "f9":  Key.f9,
    "f10":    Key.f10, "f11": Key.f11, "f12": Key.f12,
    "up":     Key.up,   "down":  Key.down,
    "left":   Key.left, "right": Key.right,
    "delete": Key.delete, "backspace": Key.backspace,
}

def resolve_key(name: str):
    """
    Turn a key name string into the correct pynput argument.

    "space"  → Key.space   (pynput special key object)
    "e"      → "e"         (single character — pynput presses it as-is)
    "f1"     → Key.f1
    "1"      → "1"
    """
    if not name:
        return None
    low = name.strip().lower()
    if low in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[low]
    if len(low) == 1:
        return low   # single character — pynput accepts strings directly
    log.warning(f"Unknown key name '{name}' — ignored")
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIG MESSAGE HANDLER
#  Called whenever the phone sends {"type":"config", ...}
# ══════════════════════════════════════════════════════════════════════════════

def apply_config(data: dict) -> None:
    """
    Update MOUSE_SENSITIVITY and BUTTON_MAP in place from a config message.
    Changes take effect on the very next controller state frame.
    """
    global MOUSE_SENSITIVITY, BUTTON_MAP

    # ── Mouse sensitivity ─────────────────────────────────────────────────────
    if "mouseSensitivity" in data:
        try:
            new_sens = float(data["mouseSensitivity"])
            if 0 < new_sens <= 20:          # sanity-clamp
                MOUSE_SENSITIVITY = new_sens
                log.info(f"⚙  Sensitivity → {MOUSE_SENSITIVITY}")
        except (TypeError, ValueError):
            pass

    # ── Button map ────────────────────────────────────────────────────────────
    if "buttonMap" in data and isinstance(data["buttonMap"], dict):
        for btn, key_name in data["buttonMap"].items():
            if btn not in ("A", "B", "X", "Y"):
                continue
            resolved = resolve_key(str(key_name))
            if resolved is not None:
                # Release the old key if it was held before swapping
                old_key = BUTTON_MAP.get(btn)
                if btn in _held_buttons and old_key is not None:
                    try:    _keyboard.release(old_key)
                    except Exception: pass
                    _held_buttons.discard(btn)

                BUTTON_MAP[btn] = resolved
                log.info(f"⚙  Button {btn} → {key_name}")

    _print_current_map()


def _print_current_map() -> None:
    """Log the active button map in a readable one-liner."""
    def name(v):
        for k, obj in _SPECIAL_KEYS.items():
            if obj == v: return k.upper()
        return str(v).upper()

    mapping = "  ".join(f"{b}:{name(k)}" for b, k in BUTTON_MAP.items())
    log.info(f"⚙  Active map:  {mapping}  |  sens={MOUSE_SENSITIVITY}")

# ══════════════════════════════════════════════════════════════════════════════
#  INPUT CONTROLLERS  (pynput)
# ══════════════════════════════════════════════════════════════════════════════

_keyboard = KeyboardController()
_mouse    = MouseController()

_held_wasd:    set[str] = set()
_held_buttons: set[str] = set()


def apply_state(data: dict) -> None:
    """Translate one controller-state dict into OS keyboard + mouse events."""

    dz = DEADZONE

    # ── Left joystick → WASD ──────────────────────────────────────────────────
    lx = float(data.get("leftJoy",  {}).get("x", 0))
    ly = float(data.get("leftJoy",  {}).get("y", 0))

    want: set[str] = set()
    if ly < -dz: want.add("w")
    if ly >  dz: want.add("s")
    if lx < -dz: want.add("a")
    if lx >  dz: want.add("d")

    for k in want - _held_wasd:
        _keyboard.press(k)
        _held_wasd.add(k)

    for k in (_held_wasd & {"w", "a", "s", "d"}) - want:
        _keyboard.release(k)
        _held_wasd.discard(k)

    # ── Right joystick → mouse look ───────────────────────────────────────────
    rx = float(data.get("rightJoy", {}).get("x", 0))
    ry = float(data.get("rightJoy", {}).get("y", 0))

    if abs(rx) > dz or abs(ry) > dz:
        # Quadratic curve — fine precision near centre, fast sweeps at edges
        # Sensitivity is live from phone slider
        dx = int(rx * abs(rx) * MOUSE_SENSITIVITY)
        dy = int(ry * abs(ry) * MOUSE_SENSITIVITY)
        _mouse.move(dx, dy)

    # ── ABXY buttons ──────────────────────────────────────────────────────────
    buttons = data.get("buttons", {})

    for btn, mapped_key in BUTTON_MAP.items():
        pressed = bool(buttons.get(btn, False))

        if pressed and btn not in _held_buttons:
            _keyboard.press(mapped_key)
            _held_buttons.add(btn)

        elif not pressed and btn in _held_buttons:
            _keyboard.release(mapped_key)
            _held_buttons.discard(btn)


def release_all() -> None:
    """Release everything held — called on every disconnect."""
    for k in list(_held_wasd):
        try:    _keyboard.release(k)
        except Exception: pass
    _held_wasd.clear()

    for btn in list(_held_buttons):
        mapped = BUTTON_MAP.get(btn)
        if mapped:
            try:    _keyboard.release(mapped)
            except Exception: pass
    _held_buttons.clear()

# ══════════════════════════════════════════════════════════════════════════════
#  TERMINAL DISPLAY
# ══════════════════════════════════════════════════════════════════════════════

def print_header(room_code: str) -> None:
    url = f"{PAGES_URL}?room={room_code}"
    W   = 56

    print()
    print("═" * W)
    print("  🎮  CLOUD CONTROLLER  —  PC HOST")
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
        print("  ⚠  QR display unavailable.")
        print("  Install with:  pip install qrcode")
        print(f"\n  Open this URL on your phone:  {url}")

    print("─" * W)
    print("  Sensitivity slider and button remapping on the phone")
    print("  Changes take effect instantly — no restart needed")
    print("═" * W)
    print()

# ══════════════════════════════════════════════════════════════════════════════
#  WEBSOCKET CLIENT
# ══════════════════════════════════════════════════════════════════════════════

async def run(room_code: str) -> None:
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
                        f"✅  Joined room '{msg.get('room')}'  "
                        f"as '{msg.get('role')}'"
                    )
                    print(f"\n  ✅  Room '{room_code}' is live.  "
                          f"Waiting for phone to connect…\n")
                else:
                    log.warning(f"Unexpected first message: {msg}")

                backoff = 2  # reset on successful connect

                # ── Process incoming messages ─────────────────────────────────
                async for message in ws:
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        continue

                    # ── Config message — update settings live ─────────────────
                    if data.get("type") == "config":
                        apply_config(data)
                        continue

                    # ── Controller state — must contain joystick data ──────────
                    if "leftJoy" not in data and "rightJoy" not in data:
                        continue   # skip unknown message types

                    apply_state(data)

        except (websockets.ConnectionClosed,
                ConnectionRefusedError,
                OSError) as e:
            log.warning(f"Connection lost: {e}")

        except asyncio.TimeoutError:
            log.warning("Connection timed out.")

        finally:
            release_all()

        log.info(f"Reconnecting in {backoff}s…")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 30)

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    room_code = generate_room_code()
    print_header(room_code)
    _print_current_map()

    try:
        asyncio.run(run(room_code))
    except KeyboardInterrupt:
        release_all()
        print("\n  Controller stopped.  All keys released.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()