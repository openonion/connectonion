"""
Purpose: Agent-side relay client for registering and serving via central relay server

Lifecycle (Agent Side):
  1. connect(relay_url) opens WebSocket to /ws/announce
  2. send_announce() sends ANNOUNCE message to register agent
  3. serve_loop() waits for INPUT messages from relay
  4. On INPUT: task_handler(prompt) processes → sends OUTPUT back
  5. Heartbeat: re-sends ANNOUNCE every 60s to stay registered

Message Flow:
  Agent → ANNOUNCE → Relay (registers in active_connections)
  Client → INPUT → Relay → forwards to Agent's WebSocket
  Agent → OUTPUT → Relay → forwards to Client's /ws/input connection

Protocol:
  ANNOUNCE: {type, address, summary, endpoints, signature, timestamp}
  INPUT:    {type, input_id, prompt, from_address?, session?}
  OUTPUT:   {type, input_id, result, session?}
  TODO: Adopt WebRTC-style ICE candidates (host/srflx/relay) and connectivity
        checks so clients can prefer direct endpoints when possible.

Related Files:
  - oo-api/relay/routes.py: Relay server that receives these messages
  - connectonion/network/connect.py: Client-side (sends INPUT, receives OUTPUT)
  - connectonion/network/host/server.py: Uses this for relay registration

LLM-Note:
  Dependencies: imports from [json, asyncio, typing, websockets]
  Data flow: connect() → /ws/announce → serve_loop() → INPUT → task_handler → OUTPUT
  State/Effects: WebSocket connection to relay | heartbeat every 60s
  Integration: exposes connect(), send_announce(), wait_for_task(), serve_loop()
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
    # TODO: Future connection metadata (observed_ip, ICE candidates) should be
    #       attached to ANNOUNCE so relay can return best endpoints to clients.
    # ping_interval=None: WebSocket-level PING frames don't survive the
    # Cloudflare edge in front of the relay, so the default 20s/20s timeout
    # tears down healthy connections after ~40s. We disable the library's
    # ping and rely on the ANNOUNCE heartbeat in serve_loop instead — if that
    # send fails, the outer reconnect loop catches it.
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
    task_handler,
    heartbeat_interval: int = 60,
    addr_data: Dict[str, Any] = None,
    local_port: int = None,
):
    """
    Main serving loop for agent.

    This handles:
    - Initial ANNOUNCE
    - Periodic heartbeat ANNOUNCE (every 60s) with fresh signature
    - Receiving tagged session messages from the relay proxy and piping them
      to the agent's own local /ws endpoint (which implements the full
      CONNECT/CONNECTED/INPUT/streaming/OUTPUT protocol).
    - Legacy one-shot INPUT → task_handler → OUTPUT (backward compat).

    Args:
        websocket: WebSocket connection from connect()
        announce_message: ANNOUNCE message dict (initial message)
        task_handler: Async function (prompt: str) -> str (legacy path)
        heartbeat_interval: Seconds between heartbeat ANNOUNCEs
        addr_data: Agent address data for re-signing heartbeat messages
        local_port: Local HTTP port where the agent's /ws endpoint listens.
            Required for the relay proxy session path; if None, the proxy
            path is disabled and only the legacy one-shot path works.
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

    # sid -> asyncio.Queue of inbound messages from relay (for this session)
    sessions: Dict[str, asyncio.Queue] = {}

    async def _run_session(sid: str, first_msg: Dict[str, Any]):
        """Open a loopback WS to the local /ws endpoint and pump messages."""
        if local_port is None:
            raise RuntimeError("local_port required for relay proxy sessions")
        local_url = f"ws://127.0.0.1:{local_port}/ws"
        queue = sessions[sid]
        try:
            async with websockets.connect(local_url) as local_ws:
                # Forward first message (strip relay-internal fields)
                await local_ws.send(json.dumps(_strip_relay_fields(first_msg)))

                async def pump_relay_to_local():
                    while True:
                        msg = await queue.get()
                        if msg is None or msg.get("_relay_event") == "close":
                            return
                        await local_ws.send(json.dumps(_strip_relay_fields(msg)))

                async def pump_local_to_relay():
                    async for raw in local_ws:
                        msg = json.loads(raw)
                        msg["_relay_sid"] = sid
                        await websocket.send(json.dumps(msg))

                t_in = asyncio.create_task(pump_relay_to_local())
                t_out = asyncio.create_task(pump_local_to_relay())
                done, pending = await asyncio.wait(
                    {t_in, t_out}, return_when=asyncio.FIRST_COMPLETED
                )
                for t in pending:
                    t.cancel()
        finally:
            sessions.pop(sid, None)

    # Main loop
    while True:
        try:
            task = await wait_for_task(websocket, timeout=heartbeat_interval)

            # Relay proxy session path (new)
            sid = task.get("_relay_sid")
            if sid:
                if sid in sessions:
                    await sessions[sid].put(task)
                else:
                    sessions[sid] = asyncio.Queue()
                    asyncio.create_task(_run_session(sid, task))
                continue

            # Legacy one-shot INPUT → OUTPUT path
            if task.get("type") == "INPUT":
                console.print(f"{prefix} [dim]Input received[/dim]")
                result = await task_handler(task["prompt"])
                output_message = {
                    "type": "OUTPUT",
                    "input_id": task["input_id"],
                    "result": result,
                }
                await websocket.send(json.dumps(output_message))
                console.print(f"{prefix} [green]Output sent[/green]")

            elif task.get("type") == "ERROR":
                console.print(f"{prefix} [red]Relay error: {task.get('error')}[/red]")

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


def _strip_relay_fields(msg: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal _relay_* tags before handing off to the local handler."""
    return {k: v for k, v in msg.items() if not k.startswith("_relay_")}
