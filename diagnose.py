"""
Cloud Controller — Connection Diagnostics
══════════════════════════════════════════
Run this on your PC to find exactly where the connection is failing.

Usage:
    python diagnose.py

It tests each step independently and tells you exactly what to fix.
"""

import asyncio
import json
import sys
import time
import urllib.request
import urllib.error

RELAY_WS_URL     = "wss://mobile-controller-relay.onrender.com/ws"
RELAY_HEALTH_URL = "https://mobile-controller-relay.onrender.com/health"

W = 56

def line(char="─"): print(char * W)
def ok(msg):   print(f"  ✅  {msg}")
def fail(msg): print(f"  ❌  {msg}")
def info(msg): print(f"  ℹ   {msg}")
def warn(msg): print(f"  ⚠   {msg}")


# ══════════════════════════════════════════════════════
# TEST 1 — Python packages installed?
# ══════════════════════════════════════════════════════
def test_packages():
    print("\n[1/4]  Checking installed packages…")
    line()
    all_ok = True

    for pkg, import_name in [
        ("websockets", "websockets"),
        ("pynput",     "pynput"),
        ("qrcode",     "qrcode"),
    ]:
        try:
            __import__(import_name)
            ok(f"{pkg} installed")
        except ImportError:
            fail(f"{pkg} NOT installed  →  run:  pip install {pkg}")
            all_ok = False

    return all_ok


# ══════════════════════════════════════════════════════
# TEST 2 — Can we reach the health endpoint?
# ══════════════════════════════════════════════════════
def test_health():
    print("\n[2/4]  Pinging relay health endpoint…")
    line()
    info(f"URL: {RELAY_HEALTH_URL}")

    for attempt in range(1, 7):
        try:
            t0 = time.monotonic()
            with urllib.request.urlopen(RELAY_HEALTH_URL, timeout=15) as r:
                elapsed = time.monotonic() - t0
                body    = r.read().decode().strip()
                ok(f"HTTP {r.status}  |  body: '{body}'  |  {elapsed:.1f}s")
                if "OK" in body:
                    ok("Relay server is awake and healthy")
                    return True
                else:
                    warn(f"Unexpected response body: {body}")
                    return True   # server responded, something is odd

        except urllib.error.HTTPError as e:
            fail(f"HTTP error {e.code}: {e.reason}")
            return False

        except urllib.error.URLError as e:
            if attempt < 6:
                warn(f"Attempt {attempt}/6 failed ({e.reason}) — waiting 10 s for server to wake…")
                time.sleep(10)
            else:
                fail(f"Cannot reach health endpoint after 6 attempts: {e.reason}")
                print()
                print("  Possible causes:")
                print("  • Render service is not deployed / build failed")
                print("  • Wrong URL in this script")
                print("  • Your internet connection is offline")
                print()
                print("  Check your Render dashboard:")
                print("  https://dashboard.render.com")
                return False

        except Exception as e:
            fail(f"Unexpected error: {e}")
            return False

    return False


# ══════════════════════════════════════════════════════
# TEST 3 — Can we open a WebSocket connection?
# ══════════════════════════════════════════════════════
async def _ws_connect_test():
    import websockets
    try:
        t0 = time.monotonic()
        async with websockets.connect(
            RELAY_WS_URL,
            open_timeout=20,
        ) as ws:
            elapsed = time.monotonic() - t0
            ok(f"WebSocket connected in {elapsed:.1f}s")
            return ws, None
    except Exception as e:
        elapsed = time.monotonic() - t0
        return None, (type(e).__name__, str(e), elapsed)

def test_websocket():
    print("\n[3/4]  Testing WebSocket connection…")
    line()
    info(f"URL: {RELAY_WS_URL}")

    ws, error = asyncio.run(_ws_connect_test())
    if error:
        etype, emsg, elapsed = error
        fail(f"WebSocket failed after {elapsed:.1f}s")
        fail(f"Exception: {etype}: {emsg}")
        print()

        if "InvalidHandshake" in etype or "InvalidUpgrade" in etype:
            print("  CAUSE: The relay server is NOT running aiohttp.")
            print("  The old websockets-library server.py is still deployed.")
            print()
            print("  FIX:")
            print("  1. Replace server.py on GitHub with the aiohttp version")
            print("  2. Replace requirements.txt with just:  aiohttp==3.9.5")
            print("  3. Trigger a redeploy on Render")

        elif "TimeoutError" in etype or elapsed > 15:
            print("  CAUSE: Server is still waking up (cold start).")
            print("  FIX:  Wait 30 s and run diagnose.py again.")

        elif "ConnectionRefused" in etype:
            print("  CAUSE: Nothing is listening on that port.")
            print("  FIX:  Check Render dashboard — service may have crashed.")

        else:
            print("  CAUSE: Unknown. Check Render logs for errors.")

        return False

    return True


# ══════════════════════════════════════════════════════
# TEST 4 — Can we join a room and get confirmation?
# ══════════════════════════════════════════════════════
async def _join_test():
    import websockets
    result = {"joined": False, "error": None, "response": None}

    try:
        async with websockets.connect(RELAY_WS_URL, open_timeout=20) as ws:
            join_msg = json.dumps({"type": "join", "room": "DIAG-00", "role": "pc"})
            await ws.send(join_msg)
            ok("Join message sent")

            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=10)
                data = json.loads(raw)
                result["response"] = data

                if data.get("type") == "joined":
                    result["joined"] = True
                else:
                    result["error"] = f"Unexpected response: {data}"

            except asyncio.TimeoutError:
                result["error"] = "Timed out waiting for join confirmation (10 s)"

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result

def test_join():
    print("\n[4/4]  Testing room join handshake…")
    line()

    result = asyncio.run(_join_test())

    if result["joined"]:
        ok(f"Room join confirmed:  {result['response']}")
        return True
    else:
        fail(f"Join failed:  {result['error']}")
        resp = result.get("response")
        if resp:
            info(f"Server response was: {resp}")
        print()
        print("  CAUSE: Server accepted the WebSocket but rejected the join.")
        print("  This usually means the server.py room logic has a bug.")
        return False


# ══════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════
def main():
    print()
    print("═" * W)
    print("  CLOUD CONTROLLER — DIAGNOSTICS")
    print("═" * W)

    # Test 1
    if not test_packages():
        print("\n  ⛔  Fix missing packages first, then re-run diagnose.py")
        sys.exit(1)

    # Test 2
    if not test_health():
        print("\n  ⛔  Fix the health endpoint first, then re-run diagnose.py")
        sys.exit(1)

    # Test 3
    if not test_websocket():
        print("\n  ⛔  Fix the WebSocket connection first, then re-run diagnose.py")
        sys.exit(1)

    # Test 4
    if not test_join():
        print("\n  ⛔  Fix the join handshake, then re-run diagnose.py")
        sys.exit(1)

    print()
    line("═")
    print("  ✅  ALL TESTS PASSED")
    print("  The relay is working correctly.")
    print("  Run client.py — it should connect immediately.")
    line("═")
    print()


if __name__ == "__main__":
    main()