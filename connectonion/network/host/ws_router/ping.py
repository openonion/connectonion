"""
Purpose: WebSocket-level keepalive — send PING every 30s so idle WS connections aren't reaped by NAT/proxy
LLM-Note:
  Dependencies: imports from [asyncio] | imported by [.session as ping_loop coroutine wrapped in asyncio.create_task]
  Data flow: infinite loop — sleep 30s → send_msg({"type": "PING"})
  State/Effects: stateless | runs as an asyncio.Task spawned in run_session, cancelled in run_session's finally
  Integration: ping_loop(send_msg) — coroutine factory; caller wraps in create_task | enable_ping=False for relay path (ANNOUNCE heartbeat covers it)
  Performance: trivial — one async sleep + one send per 30s
  Errors: send_msg failure propagates → task fails → run_session finally still cancels it cleanly
"""
import asyncio


async def ping_loop(send_msg):
    """Send PING every 30s to keep connection alive."""
    while True:
        await asyncio.sleep(30)
        await send_msg({"type": "PING"})
