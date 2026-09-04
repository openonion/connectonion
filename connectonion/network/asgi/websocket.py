"""ASGI WebSocket transport adapter.

Purpose: Translate ASGI websocket events into the JSON message contract consumed by host.ws_router so the same router works behind any ASGI server (uvicorn, hypercorn, etc.).
LLM-Note:
  Dependencies: imports from [json, rich.console, .http.pydantic_json_encoder, ..host.ws_router.run_ws_session] | imported by [network/asgi/__init__.py (create_app), network/host/server.py via the ASGI app it builds] | tested by [tests/unit/test_asgi.py]
  Data flow: ASGI scope/receive/send for path "/ws" → accept handshake → wrap receive/send into recv_msg() / send_msg() that JSON-decode/encode payloads (using pydantic_json_encoder for Pydantic models) → delegate to run_ws_session(...) which drives CONNECT → CONNECTED → INPUT → streaming events → OUTPUT
  State/Effects: prints connect/disconnect lines via rich.Console with active session count from registry | rejects non-/ws paths with close code 4004 | sends ERROR frame back to client on JSON decode failure (with snippet, max 200 chars)
  Integration: exposes handle_websocket(scope, receive, send, *, route_handlers, storage, registry, trust, blacklist=None, whitelist=None) | the ws_router contract is owned by host/ws_router/__init__.py
  Performance: per-connection async loop; one task per websocket | JSON decode is per-message
  Errors: malformed JSON returns ERROR frame with parse details and offending snippet — does not raise | downstream errors bubble from run_ws_session
Protocol: CONNECT → CONNECTED → INPUT → streaming events → OUTPUT
See docs/network/websocket-protocol.md for full specification.
"""

import json

from rich.console import Console

from ..host.ws_router import run_ws_session
from .http import pydantic_json_encoder

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
                raw = msg.get("text", "")
                try:
                    return json.loads(raw or "{}")
                except json.JSONDecodeError as e:
                    # Surface the actual parse error + the offending input so
                    # the client can locate the bug rather than guessing.
                    snippet = raw if len(raw) <= 200 else raw[:200] + "...(truncated)"
                    await send_msg({
                        "type": "ERROR",
                        "message": f"Invalid JSON: {e.msg} at line {e.lineno} col {e.colno} (pos {e.pos})",
                        "received": snippet,
                    })
                    continue

    send_msg, recv_msg = await _maybe_seal(send_msg, recv_msg, route_handlers)
    if send_msg is None:
        await send({"type": "websocket.close", "code": 4003})
        return

    await run_ws_session(
        send_msg, recv_msg,
        route_handlers=route_handlers,
        storage=storage,
        registry=registry,
        trust=trust,
        blacklist=blacklist,
        whitelist=whitelist,
        transport="direct",
    )

    console.print(f"[dim]⚡ ws-[/dim] [dim]({registry.count()} active)[/dim]")


async def _maybe_seal(send_msg, recv_msg, route_handlers):
    """Seal the socket if the client opens with SEAL; pass an older client through.

    The first frame decides. SEAL is answered with SEALED_OK and from then on
    both adapters carry sealed frames, so the router never sees the
    difference. Anything else is handed to the router unchanged, as the first
    frame it reads. A SEAL that does not verify closes the socket: an
    unauthenticated stranger gets no second try at a plaintext CONNECT.
    """
    from ..sealed import SEAL, SealError, SealRefused, host_accept

    first = await recv_msg()
    if first is None:
        return None, None
    if first.get("type") != SEAL:
        async def recv_with_first():
            nonlocal first
            if first is not None:
                frame, first = first, None
                return frame
            return await recv_msg()
        return send_msg, recv_with_first

    identity = route_handlers.get("identity")
    if identity is None:
        await send_msg({"type": "ERROR", "message": "this host cannot seal"})
        return None, None
    try:
        reply, channel = host_accept(first, identity)
    except SealRefused as refused:
        await send_msg({"type": "ERROR", "message": f"seal refused: {refused}"})
        return None, None
    await send_msg(reply)

    async def send_sealed(data):
        await send_msg(channel.seal(data, default=pydantic_json_encoder))

    async def recv_sealed():
        frame = await recv_msg()
        if frame is None:
            return None
        try:
            return channel.open(frame)
        except SealError as failed:
            # A frame that does not open is a break-in or a bug; either way
            # the session ends here rather than guessing.
            await send_msg({"type": "ERROR", "message": f"sealed frame rejected: {failed}"})
            return None

    return send_sealed, recv_sealed
