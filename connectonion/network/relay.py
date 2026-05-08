"""
Purpose: Agent-side relay client — registers with central relay over WebSocket and serves multi-session traffic via local /ws loopback
LLM-Note:
  Dependencies: imports from [json, asyncio, websockets, typing] | imported by [agent host startup code that opts into relay mode] | tested by [tests/unit/test_relay.py, tests/e2e/test_relay_e2e.py]
  Data flow: connect(relay_url) opens WS to /ws/announce → send_announce() registers agent → serve_loop() reads frames, routes by session_id → session_handler callback runs the per-session WS protocol (CONNECT/INPUT/OUTPUT...) | response frames carry session_id back through relay to the right client
  State/Effects: maintains a long-lived WebSocket to relay | per-session async tasks spawned by serve_loop | heartbeat re-sends ANNOUNCE every 60s to stay registered
  Integration: exposes connect(relay_url), send_announce(ws, agent_address, ...), serve_loop(ws, session_handler) | session_handler signature mirrors direct ASGI WS handler so run_ws_session is reusable
  Performance: single relay WebSocket fans out to N concurrent client sessions | each session_handler runs in its own task, isolated state via session_id routing
  Errors: relay disconnect propagates to caller (let it crash; supervisor reconnects) | malformed frames raise to serve_loop for visibility

Message Flow:
  Agent → ANNOUNCE → Relay (registers in active_connections)
  Client → CONNECT/INPUT → Relay → forwards to Agent's announce WebSocket
  serve_loop routes by session_id → session_handler runs protocol directly
  Responses (with session_id) → Relay → Client
"""

import json
import asyncio
from typing import Dict, Any
import websockets


async def connect(relay_url: str = "wss://oo.openonion.ai"):
    """
    Connect to relay's announce endpoint.

    Args:
        relay_url: Relay server base URL (default: production relay)

    Returns:
        WebSocket connection object

    Example:
        >>> ws = await connect()
        >>> # Now use ws for sending/receiving
    """
    ws_url = f"{relay_url.rstrip('/')}/ws/announce"
    # ping_interval=None: Cloudflare drops WS PING frames; ANNOUNCE heartbeat
    # serves as keep-alive instead. See docs/network/protocol/agent-relay-protocol.md.
    return await websockets.connect(ws_url, ping_interval=None)


async def send_announce(websocket, announce_message: Dict[str, Any]):
    """
    Send ANNOUNCE message through WebSocket.

    Args:
        websocket: WebSocket connection from connect()
        announce_message: Dict from create_announce_message()

    Note:
        Server responds with error message only if something went wrong.
        No response = success (per protocol spec)

    Example:
        >>> from . import announce, address
        >>> addr = address.load()
        >>> msg = announce.create_announce_message(addr, "My agent", [])
        >>> await send_announce(ws, msg)
    """
    message_json = json.dumps(announce_message)
    await websocket.send(message_json)


async def recv_relay_msg(websocket, timeout: float = None) -> Dict[str, Any]:
    """
    Wait for next INPUT message from relay.

    Args:
        websocket: WebSocket connection from connect()
        timeout: Optional timeout in seconds (None = wait forever)

    Returns:
        INPUT message dict:
        {
            "type": "INPUT",
            "input_id": "abc123...",
            "prompt": "Translate hello to Spanish",
            "from_address": "0x..."
        }

    Raises:
        asyncio.TimeoutError: If timeout expires
        websockets.exceptions.ConnectionClosed: If connection lost

    Example:
        >>> msg = await recv_relay_msg(ws)
        >>> print(msg["prompt"])
        Translate hello to Spanish
    """
    if timeout:
        data = await asyncio.wait_for(websocket.recv(), timeout=timeout)
    else:
        data = await websocket.recv()

    message = json.loads(data)
    return message


async def send_response(
    websocket,
    input_id: str,
    result: str,
    success: bool = True
):
    """
    Send output response back to relay.

    Args:
        websocket: WebSocket connection from connect()
        input_id: ID from INPUT message
        result: Agent's response/output
        success: Whether task succeeded (default True)

    Example:
        >>> msg = await recv_relay_msg(ws)
        >>> result = agent.input(msg["prompt"])
        >>> await send_response(ws, msg["input_id"], result)
    """
    response_message = {
        "type": "OUTPUT",
        "input_id": input_id,
        "result": result,
        "success": success
    }

    message_json = json.dumps(response_message)
    await websocket.send(message_json)


async def _run_session(session_id, first_msg, sessions, relay_ws, session_handler):
    """Create relay transport adapters and run protocol handler for one session."""
    from .asgi.http import pydantic_json_encoder

    q = sessions[session_id]
    await q.put(first_msg)

    async def send_msg(data):
        data["session_id"] = session_id
        await relay_ws.send(json.dumps(data, default=pydantic_json_encoder))

    async def recv_msg():
        try:
            msg = await asyncio.wait_for(q.get(), timeout=300)
        except asyncio.TimeoutError:
            # 5min idle = client vanished without close. Translate the asyncio
            # timer signal into the run_ws_session contract (None = end of stream)
            # so the session loop exits cleanly. Not a swallowed error — this
            # IS the protocol-level idle-timeout mechanism.
            return None
        if msg is None or msg.get("type") == "close":
            return None
        return msg

    # finally (no except): always remove this session_id's queue from the
    # shared dict, no matter how session_handler ended (normal return /
    # exception / asyncio cancel). Without finally the dict leaks per-session
    # queue entries on any non-normal exit.
    try:
        await session_handler(send_msg, recv_msg)
    finally:
        del sessions[session_id]


async def serve_loop(
    websocket,
    announce_message: Dict[str, Any],
    *,
    heartbeat_interval: int = 60,
    addr_data: Dict[str, Any] = None,
    session_handler=None,
):
    """Main serving loop for agent.

    Receives messages from relay, routes by session_id to per-session
    protocol handlers (no loopback WebSocket).

    Args:
        websocket: WebSocket connection from connect()
        announce_message: ANNOUNCE message dict (initial message)
        heartbeat_interval: Seconds between heartbeat ANNOUNCEs
        addr_data: Agent address data for re-signing heartbeat messages
        session_handler: async (send_msg, recv_msg) -> None, runs protocol for one session
    """
    from . import announce as announce_module
    from rich.console import Console
    console = Console()
    prefix = "[magenta]\\[host][/magenta]"

    await send_announce(websocket, announce_message)

    summary = announce_message.get("summary", "")
    endpoints = announce_message.get("endpoints", [])
    relay_url = announce_message.get("relay")

    sessions: Dict[str, asyncio.Queue] = {}

    # Two except branches below are control-flow signals, not error swallowing.
    # Anything else (malformed JSON, OSError, real bugs) propagates out → kills
    # serve_loop → kills relay_loop in server.py → host process exposes the bug.
    # That's intentional "let it crash" — we only catch the two events that ARE
    # part of normal operation.
    while True:
        try:
            msg = await recv_relay_msg(websocket, timeout=heartbeat_interval)

            if msg.get("type") == "ERROR":
                console.print(f"{prefix} [red]Relay error: {msg.get('error')}[/red]")
                continue

            session_id = msg["session_id"]
            if session_id in sessions:
                await sessions[session_id].put(msg)
            else:
                sessions[session_id] = asyncio.Queue()
                asyncio.create_task(_run_session(session_id, msg, sessions, websocket, session_handler))

        except asyncio.TimeoutError:
            # heartbeat_interval (60s) elapsed with no incoming frame.
            # Heart-beat path: refresh ANNOUNCE so relay's stale-agent cleanup
            # (≈120s without ANNOUNCE) doesn't drop our registration. NOT an
            # error — this is how we keep the registration alive on idle hosts.
            # Stay in the loop.
            if addr_data:
                fresh_announce = announce_module.create_announce_message(
                    addr_data, summary, endpoints=endpoints, relay=relay_url
                )
                await send_announce(websocket, fresh_announce)
            else:
                announce_message["timestamp"] = int(asyncio.get_event_loop().time())
                await send_announce(websocket, announce_message)
            console.print(f"{prefix} [red]♥[/red]")

        except websockets.exceptions.ConnectionClosed:
            # Relay WS closed cleanly (relay redeployed, network blip, NAT idle
            # cut). Wake every per-session recv_msg by putting None into its
            # queue so children exit cleanly, then break out — server.py's
            # relay_loop sleeps 1s and reconnects.
            for q in sessions.values():
                await q.put(None)
            console.print(f"{prefix} [dim]Relay disconnected[/dim]")
            break
