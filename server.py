"""
Cloud WebSocket Relay Server — aiohttp edition
═══════════════════════════════════════════════
Deploy this on Render. Uses aiohttp which works correctly
behind Render's reverse proxy (the websockets library does not).

Endpoints
─────────
  GET /          → health check (returns 200 OK)
  GET /health    → health check (returns 200 OK)
  GET /ws        → WebSocket endpoint ← clients connect here

Room protocol
─────────────
  Every client sends a join message first:
    {"type": "join", "room": "TIGER-42", "role": "phone"}
    {"type": "join", "room": "TIGER-42", "role": "pc"}

  Server replies:
    {"type": "joined", "room": "TIGER-42", "role": "phone"}

  All subsequent messages are forwarded to the other
  member of the same room only.
"""

import json
import logging
import os
from collections import defaultdict

import aiohttp
from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger(__name__)

# ── Room registry ──────────────────────────────────────────────────────────────
# { "TIGER-42": {"phone": ws_or_None, "pc": ws_or_None} }
rooms: dict = defaultdict(lambda: {"phone": None, "pc": None})


# ── Health check ───────────────────────────────────────────────────────────────
# Render hits GET / to verify the service is alive.
# This also lets the client wake up a sleeping free-tier instance
# by hitting /health before opening a WebSocket.
async def health(request: web.Request) -> web.Response:
    active_rooms   = len(rooms)
    active_clients = sum(
        (1 if r["phone"] else 0) + (1 if r["pc"] else 0)
        for r in rooms.values()
    )
    return web.Response(
        text=f"OK  |  rooms={active_rooms}  clients={active_clients}",
        status=200,
    )


# ── WebSocket handler ──────────────────────────────────────────────────────────
async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse(heartbeat=20)
    await ws.prepare(request)

    room_code: str | None = None
    role:      str | None = None

    client_ip = request.headers.get("X-Forwarded-For", request.remote)
    log.info(f"🔌  New connection from {client_ip}")

    try:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                # ── Parse incoming message ────────────────────────────────────
                try:
                    data = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue   # drop malformed messages silently

                # ── Handle join (must be first message) ──────────────────────
                if data.get("type") == "join" and room_code is None:
                    room_code = str(data.get("room", "")).strip().upper()
                    role      = str(data.get("role", "")).strip().lower()

                    if not room_code or role not in ("phone", "pc"):
                        await ws.send_str(json.dumps({
                            "type": "error",
                            "msg":  "First message must be: "
                                    '{"type":"join","room":"TIGER-42","role":"phone"}'
                        }))
                        continue

                    rooms[room_code][role] = ws
                    log.info(
                        f"✅  [{room_code}]  {role} joined  "
                        f"(phone={rooms[room_code]['phone'] is not None}  "
                        f"pc={rooms[room_code]['pc'] is not None})"
                    )

                    await ws.send_str(json.dumps({
                        "type": "joined",
                        "room": room_code,
                        "role": role,
                    }))
                    continue

                # ── Ignore everything before a valid join ─────────────────────
                if room_code is None:
                    continue

                # ── Forward to the other side of the room ─────────────────────
                room = rooms[room_code]
                peer = room.get("pc" if role == "phone" else "phone")

                if peer and not peer.closed:
                    try:
                        log.info(f"[{room_code}] FORWARDING TO {('pc' if role=='phone' else 'phone')}: {msg.data}")
                        await peer.send_str(msg.data)
                    except Exception:
                        pass   # peer disconnected between the check and the send

            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                break

    except Exception as e:
        log.warning(f"WS handler error: {e}")

    finally:
        # ── Clean up room entry ───────────────────────────────────────────────
        if room_code and role:
            if rooms[room_code].get(role) is ws:
                rooms[room_code][role] = None
                log.info(f"👋  [{room_code}]  {role} disconnected")

            # Delete room when both sides have left
            if rooms[room_code]["phone"] is None and rooms[room_code]["pc"] is None:
                del rooms[room_code]
                log.info(f"🗑   [{room_code}]  room closed")
        else:
            log.info(f"👋  Connection closed (never joined a room)")

    return ws


# ── App setup ──────────────────────────────────────────────────────────────────
app = web.Application()
app.router.add_get("/",       health)
app.router.add_get("/health", health)
app.router.add_get("/ws",     websocket_handler)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    log.info(f"🚀  Relay server starting on port {port}")
    web.run_app(app, host="0.0.0.0", port=port, access_log=log)