"""ASGI WebSocket transport adapter.

Thin wrapper that creates ASGI send/recv adapters and delegates
to the message router in host/ws_router/ (a 4-file package).

Protocol: CONNECT → CONNECTED → INPUT → streaming events → OUTPUT
See docs/network/websocket-protocol.md for full specification.
"""

import json

from rich.console import Console
from .http import pydantic_json_encoder
from ..host.ws_router import run_ws_session

console = Console()


async def handle_websocket(
    scope,
    receive,
    send,
    *,
    route_handlers: dict,
    storage,
    registry,
    trust,
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Handle WebSocket connections at /ws via ASGI transport."""
    if scope["path"] != "/ws":
        await send({"type": "websocket.close", "code": 4004})
        return

    await send({"type": "websocket.accept"})
    client_ip = scope.get('client', ('?',))[0]
    console.print(f"[dim]⚡ ws+[/dim] [green]{client_ip}[/green] [dim]({registry.count()} active)[/dim]")

    async def send_msg(data):
        await send({"type": "websocket.send", "text": json.dumps(data, default=pydantic_json_encoder)})

    async def recv_msg():
        while True:
            msg = await receive()
            if msg["type"] == "websocket.disconnect":
                return None
            if msg["type"] == "websocket.receive":
                try:
                    return json.loads(msg.get("text", "{}"))
                except json.JSONDecodeError:
                    await send_msg({"type": "ERROR", "message": "Invalid JSON"})
                    continue

    await run_ws_session(
        send_msg, recv_msg,
        route_handlers=route_handlers,
        storage=storage,
        registry=registry,
        trust=trust,
        blacklist=blacklist,
        whitelist=whitelist,
    )

    console.print(f"[dim]⚡ ws-[/dim] [dim]({registry.count()} active)[/dim]")
