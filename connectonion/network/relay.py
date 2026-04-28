"""
Purpose: Agent-side relay client for registering and serving via central relay server

Lifecycle (Agent Side):
  1. connect(relay_url) opens WebSocket to /ws/announce
  2. send_announce() sends ANNOUNCE message to register agent
  3. serve_loop() receives messages from relay, routes by session_id
  4. Messages forwarded to local /ws endpoint for full protocol handling
  5. Heartbeat: re-sends ANNOUNCE every 60s to stay registered

Message Flow:
  Agent → ANNOUNCE → Relay (registers in active_connections)
  Client → CONNECT/INPUT → Relay → forwards to Agent's announce WebSocket
  Agent serve_loop → forwards to local ws://127.0.0.1:{port}/ws
  Local /ws handles full protocol (CONNECT/INPUT/streaming/OUTPUT)
  Responses (with session_id) → serve_loop → Relay → Client

Protocol:
  ANNOUNCE: {type, address, summary, endpoints, signature, timestamp}
  INPUT:    {type, input_id, prompt, from_address?, session_id, session?}
  OUTPUT:   {type, input_id, result, session_id, session?}
  All events carry session_id (injected by _pipe_ws_io in websocket.py).
  Relay and serve_loop both route by session_id — no transport-level tags.

Related Files:
  - oo-api/relay/routes.py: Relay server that forwards messages
  - connectonion/network/asgi/websocket.py: Local /ws handler (full protocol)
  - connectonion/network/connect.py: Client-side (sends INPUT, receives OUTPUT)
  - connectonion/network/host/server.py: Uses this for relay registration

LLM-Note:
  Dependencies: imports from [json, asyncio, typing, websockets]
  Data flow: connect() → /ws/announce → serve_loop() → local /ws → agent
  State/Effects: WebSocket connection to relay | heartbeat every 60s
  Integration: exposes connect(), send_announce(), wait_for_task(), serve_loop()
  Docs: docs/network/protocol/agent-relay-protocol.md
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


async def wait_for_task(websocket, timeout: float = None) -> Dict[str, Any]:
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
        >>> task = await wait_for_task(ws)
        >>> print(task["prompt"])
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
        >>> task = await wait_for_task(ws)
        >>> result = agent.input(task["prompt"])
        >>> await send_response(ws, task["input_id"], result)
    """
    response_message = {
        "type": "OUTPUT",
        "input_id": input_id,
        "result": result,
        "success": success
    }

    message_json = json.dumps(response_message)
    await websocket.send(message_json)


async def serve_loop(
    websocket,
    announce_message: Dict[str, Any],
    *,
    heartbeat_interval: int = 60,
    addr_data: Dict[str, Any] = None,
    local_port: int,
):
    """
    Main serving loop for agent.

    Receives messages from relay, routes by session_id to per-session
    loopback WebSocket connections to the local /ws endpoint.

    Args:
        websocket: WebSocket connection from connect()
        announce_message: ANNOUNCE message dict (initial message)
        heartbeat_interval: Seconds between heartbeat ANNOUNCEs
        addr_data: Agent address data for re-signing heartbeat messages
        local_port: Local HTTP port where the agent's /ws endpoint listens.
    """
    from . import announce as announce_module
    from rich.console import Console
    console = Console()
    prefix = "[magenta]\\[host][/magenta]"

    # Send initial ANNOUNCE
    await send_announce(websocket, announce_message)

    # Extract announce parameters for heartbeat re-creation
    summary = announce_message.get("summary", "")
    endpoints = announce_message.get("endpoints", [])
    relay_url = announce_message.get("relay")

    # session_id -> asyncio.Queue of inbound messages from relay
    sessions: Dict[str, asyncio.Queue] = {}

    async def _run_session(session_id: str, first_msg: Dict[str, Any]):
        """Open a loopback WS to the local /ws endpoint and pump messages."""
        local_url = f"ws://127.0.0.1:{local_port}/ws"
        queue = sessions[session_id]
        try:
            async with websockets.connect(local_url) as local_ws:
                # Forward the initial CONNECT message to local /ws
                await local_ws.send(json.dumps(first_msg))

                async def pump_relay_to_local():
                    """Relay → agent: read from queue and forward to local /ws."""
                    while True:
                        msg = await queue.get()
                        if msg is None or msg.get("type") == "close":
                            return
                        await local_ws.send(json.dumps(msg))

                async def pump_local_to_relay():
                    """Agent → client: read from local /ws and forward to relay."""
                    async for raw in local_ws:
                        # Events already include session_id (injected by _pipe_ws_io)
                        await websocket.send(raw)

                t_in = asyncio.create_task(pump_relay_to_local())
                t_out = asyncio.create_task(pump_local_to_relay())
                done, pending = await asyncio.wait(
                    {t_in, t_out}, return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending:
                    t.cancel()
        finally:
            del sessions[session_id]

    # Main loop
    while True:
        try:
            task = await wait_for_task(websocket, timeout=heartbeat_interval)

            # Handle relay-level errors (no session_id)
            if task.get("type") == "ERROR":
                console.print(f"{prefix} [red]Relay error: {task.get('error')}[/red]")
                continue

            # Route by session_id — every message must carry one
            session_id = task["session_id"]
            if session_id in sessions:
                await sessions[session_id].put(task)
            else:
                sessions[session_id] = asyncio.Queue()
                asyncio.create_task(_run_session(session_id, task))

        except asyncio.TimeoutError:
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
            console.print(f"{prefix} [dim]Relay disconnected[/dim]")
            break
