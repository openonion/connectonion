"""
Purpose: WebSocket relay client for agent-to-agent communication via central relay server using INPUT/OUTPUT protocol
LLM-Note:
  Dependencies: imports from [json, asyncio, typing, websockets] | imported by [agent.py] | tested by [tests/test_relay.py]
  Data flow: Agent.serve() → connect(relay_url) → WebSocket established → send_announce(ws, announce_msg) → serve_loop() → wait_for_task(ws) receives INPUT message from relay → task_handler(prompt) executes → send OUTPUT response via WebSocket → heartbeat re-announces every 60s
  State/Effects: maintains WebSocket connection to relay | reads incoming JSON messages (INPUT type) | writes outgoing JSON messages (OUTPUT type) | prints status to stdout | asyncio timeout for heartbeat | no file I/O
  Integration: exposes connect(relay_url), send_announce(ws, msg), wait_for_task(ws, timeout), send_response(ws, input_id, result), serve_loop(ws, announce_msg, task_handler, heartbeat_interval) | used by Agent.serve() to make agent discoverable on relay network | task_handler is async function (prompt: str) -> str | Protocol: INPUT/OUTPUT messages (not TASK/RESPONSE)
  Performance: async/await non-blocking I/O | heartbeat_interval=60s default (configurable) | timeout-based heartbeat scheduling | WebSocket maintains persistent connection
  Errors: let it crash - ImportError if websockets missing | asyncio.TimeoutError used for heartbeat timing | websockets.ConnectionClosed exits serve loop gracefully

WebSocket relay client functions.

Simple async functions for connecting to relay and exchanging messages using INPUT/OUTPUT protocol.
No classes needed - just stateless functions operating on websocket connections.
"""

import json
import asyncio
from typing import Dict, Any
import websockets


async def connect(relay_url: str = "wss://oo.openonion.ai/ws/announce"):
    """
    Connect to relay WebSocket endpoint.

    Args:
        relay_url: WebSocket URL for relay (default: production relay)

    Returns:
        WebSocket connection object

    Example:
        >>> ws = await connect()
        >>> # Now use ws for sending/receiving
    """
    return await websockets.connect(relay_url)


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
    heartbeat_interval: int = 60
):
    """
    Main serving loop for agent.

    This handles:
    - Initial ANNOUNCE
    - Periodic heartbeat ANNOUNCE (every 60s)
    - Receiving and processing TASK messages
    - Sending responses

    Args:
        websocket: WebSocket connection from connect()
        announce_message: ANNOUNCE message dict (will be re-sent for heartbeat)
        task_handler: Async function that takes (prompt: str) -> str
        heartbeat_interval: Seconds between heartbeat ANNOUNCEs (default 60)

    Example:
        >>> async def handler(prompt):
        ...     return agent.input(prompt)
        >>> await serve_loop(ws, announce_msg, handler)
    """
    # Send initial ANNOUNCE
    await send_announce(websocket, announce_message)
    print(f"✓ Announced to relay: {announce_message['address'][:12]}...")

    # Track last heartbeat time
    last_heartbeat = asyncio.get_event_loop().time()

    # Main loop
    while True:
        try:
            # Wait for message with timeout to allow heartbeat
            task = await wait_for_task(websocket, timeout=heartbeat_interval)

            # Handle INPUT message
            if task.get("type") == "INPUT":
                print(f"→ Received input: {task['input_id'][:8]}...")

                # Process with handler
                result = await task_handler(task["prompt"])

                # Send OUTPUT response
                output_message = {
                    "type": "OUTPUT",
                    "input_id": task["input_id"],
                    "result": result
                }
                await websocket.send(json.dumps(output_message))
                print(f"✓ Sent output: {task['input_id'][:8]}...")

            elif task.get("type") == "ERROR":
                print(f"✗ Error from relay: {task.get('error')}")

        except asyncio.TimeoutError:
            # Time for heartbeat ANNOUNCE
            # Update timestamp in message
            announce_message["timestamp"] = int(asyncio.get_event_loop().time())

            # Need to re-sign with new timestamp
            # For now, just send without updating signature
            # TODO: Re-sign message with new timestamp
            await send_announce(websocket, announce_message)
            print("♥ Sent heartbeat")
            last_heartbeat = asyncio.get_event_loop().time()

        except websockets.exceptions.ConnectionClosed:
            print("✗ Connection to relay closed")
            break
