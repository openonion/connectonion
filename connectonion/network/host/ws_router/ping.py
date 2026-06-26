"""
Purpose: WebSocket-level keepalive — send PING every 30s so idle WS connections aren't reaped by NAT/proxy
LLM-Note:
  Dependencies: imports from [asyncio] | imported by [.session as ping_loop coroutine wrapped in asyncio.create_task]
  Data flow: infinite loop — sleep 30s → send_msg({"type": "PING"})
  State/Effects: stateless | runs as an asyncio.Task spawned in run_ws_session, cancelled in run_ws_session's finally
  Integration: ping_loop(send_msg) — coroutine factory; caller wraps in create_task | enabled on both direct AND relay paths: the relay's ANNOUNCE heartbeat only keeps the agent↔relay link alive and never reaches the client, so the 30s client PING is still needed end-to-end (it also keeps the relay session's recv idle timer fresh via PONGs)
  Performance: trivial — one async sleep + one send per 30s
  Errors: send_msg failure propagates → task fails → run_ws_session finally still cancels it cleanly
"""
import asyncio


async def ping_loop(send_msg):
    """Send PING every 30s to keep connection alive."""
    while True:
        await asyncio.sleep(30)
        await send_msg({"type": "PING"})
