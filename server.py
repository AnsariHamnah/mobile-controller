"""
Cloud WebSocket Relay Server  —  Room Edition
═════════════════════════════════════════════
Deploy this on Render (free tier).  Replace your existing server.py entirely.

How it works
────────────
Every connection MUST send a join message as its very first message:
    {"type": "join", "room": "TIGER-42", "role": "phone"}
    {"type": "join", "room": "TIGER-42", "role": "pc"}

After joining, every subsequent message is forwarded only to
other connections that are in the same room.

Rooms are created automatically when the first member joins.
Rooms are deleted automatically when the last member leaves.

No two rooms can see each other's traffic.
"""

import asyncio
import json
import logging
import os

import websockets

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger(__name__)

# ── Room registry ─────────────────────────────────────────────────────────────
# Structure:
#   ROOMS = {
#       "TIGER-42": {ws_phone, ws_pc},
#       "NOVA-18":  {ws_phone2},
#   }
ROOMS: dict[str, set] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def room_count() -> str:
    """Return a short summary string for logging."""
    total_clients = sum(len(members) for members in ROOMS.values())
    return f"{len(ROOMS)} room(s), {total_clients} client(s)"


async def safe_send(ws, message: str) -> None:
    """Send a message, silently ignoring closed connections."""
    try:
        await ws.send(message)
    except websockets.ConnectionClosed:
        pass


# ── Main handler ──────────────────────────────────────────────────────────────

async def handler(ws, path):
    """
    Lifecycle for one WebSocket connection:

    1. Wait for the join message.
    2. Register the connection in the correct room.
    3. Forward all subsequent messages to room-mates only.
    4. On disconnect: clean up the room.
    """
    addr = ws.remote_address
    room_code: str | None = None
    role: str = "unknown"

    try:
        # ── Step 1: Expect a join message ─────────────────────────────────────
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=15)
        except asyncio.TimeoutError:
            log.warning(f"⏱  {addr} — no join message within 15 s, closing.")
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning(f"🚫  {addr} — first message was not valid JSON, closing.")
            return

        

        # Validate join message structure
        if (
            msg.get("type") != "join"
            or not isinstance(msg.get("room"), str)
            or not msg["room"].strip()
            or msg.get("role") not in ("phone", "pc")
        ):
            log.warning(f"🚫  {addr} — invalid join message: {msg}, closing.")
            return

        room_code = msg["room"].strip().upper()
        role = msg["role"]

        # ── Step 2: Register in room ──────────────────────────────────────────
        if room_code not in ROOMS:
            ROOMS[room_code] = set()
            log.info(f"🏠  Room '{room_code}' created.")

        ROOMS[room_code].add(ws)
        log.info(
            f"✅  [{room_code}] {role} joined  ({addr})  —  "
            f"room now has {len(ROOMS[room_code])} member(s)  —  {room_count()}"
        )

        # Notify the joining client that it has been accepted
        await safe_send(ws, json.dumps({"type": "joined", "room": room_code, "role": role}))

        # ── Step 3: Forward subsequent messages to room-mates ─────────────────
        async for message in ws:
            # Validate JSON before relaying (drops malformed messages silently)
            try:
                json.loads(message)
            except json.JSONDecodeError:
                log.debug(f"[{room_code}] dropped non-JSON message from {role}")
                continue

            # Only forward if there are other members in the room
            room_members = ROOMS.get(room_code, set())
            targets = room_members - {ws}

            if targets:
                await asyncio.gather(
                    *[safe_send(t, message) for t in targets],
                    return_exceptions=True,
                )

    except websockets.ConnectionClosed:
        pass  # normal disconnect

    finally:
        # ── Step 4: Clean up ──────────────────────────────────────────────────
        if room_code and room_code in ROOMS:
            ROOMS[room_code].discard(ws)

            if ROOMS[room_code]:
                log.info(
                    f"👋  [{room_code}] {role} left  ({addr})  —  "
                    f"room still has {len(ROOMS[room_code])} member(s)"
                )
            else:
                del ROOMS[room_code]
                log.info(f"🗑   Room '{room_code}' closed (empty)  —  {room_count()}")
        else:
            log.info(f"👋  {addr} disconnected (never fully joined)")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    port = int(os.environ.get("PORT", 8765))
    log.info(f"🚀  Relay server starting on port {port}")

    async with websockets.serve(
        handler,
        host="0.0.0.0",
        port=port,
        ping_interval=20,       # keepalive ping every 20 s
        ping_timeout=30,        # drop connection if no pong within 30 s
        max_size=64_000,        # 64 KB cap — controller packets are tiny
        compression=None,       # disable compression for lower latency
    ):
        log.info("✅  Server running.  Waiting for connections…")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())