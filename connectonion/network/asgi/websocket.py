"""
Purpose: WebSocket bidirectional communication for ASGI server with real-time agent I/O
LLM-Note:
  Dependencies: imports from [network/io/websocket.py, network/asgi/http.py pydantic_json_encoder, asyncio, json, queue, threading] | imported by [network/asgi/__init__.py] | tested by [tests/network/test_asgi_websocket.py]
  Data flow: handle_websocket() accepts connection → receives INPUT message with prompt+session → authenticates via route_handlers["auth"] → starts agent in background thread with WebSocketIO → agent sends events via io.log()/send() → forwards to client via websocket.send → client sends ASK_USER_RESPONSE for approvals → io receives via queue → agent resumes → returns OUTPUT with result+session_id
  State/Effects: maintains WebSocket connection during agent execution | runs agent in daemon thread (non-blocking) | uses queue.Queue for thread-safe I/O between agent and WebSocket | no persistent state (connection-scoped)
  Integration: exposes handle_websocket(scope, receive, send, route_handlers, storage, trust, blacklist, whitelist) | uses WebSocketIO for bidirectional I/O | supports session continuation (same as HTTP) | message types: INPUT (client), OUTPUT/ERROR (server), ASK_USER_RESPONSE (client), trace events (server)
  Performance: async WebSocket handling | agent runs in separate thread to avoid blocking | queue-based message passing | streams events in real-time (thinking, tool_result, approval_needed)
  Errors: sends ERROR message for invalid JSON, auth failures, missing prompt | closes connection with code 4004 for wrong path | catches exceptions in agent thread and sends ERROR
WebSocket handling for ASGI.

ASGI Protocol Types (not our custom types - this is the ASGI spec):
- websocket.connect    : ASGI sends when client wants to connect
- websocket.accept     : We send to accept the connection
- websocket.receive    : ASGI sends when client sends a message
- websocket.send       : We send to deliver a message to client
- websocket.disconnect : ASGI sends when client disconnects
- websocket.close      : We send to close the connection

Our Application Types (sent inside websocket.send text payload):
- INPUT              : Client sends prompt
- OUTPUT             : Server sends final result
- ERROR              : Server sends error message
- ASK_USER_RESPONSE  : Client responds to approval request
- (trace events)     : thinking, tool_result, approval_needed, etc.
"""

import asyncio
import json
import queue
import threading

from ..io import WebSocketIO
# Import pydantic_json_encoder for serializing Pydantic models (e.g., TokenUsage) in WebSocket responses
from .http import pydantic_json_encoder


async def handle_websocket(
    scope,
    receive,
    send,
    *,
    route_handlers: dict,
    storage,
    trust: str,
    blacklist: list | None = None,
    whitelist: list | None = None,
):
    """Handle WebSocket connections at /ws.

    Supports bidirectional communication via IO interface:
    - Agent sends events via agent.io.log() / agent.io.send()
    - Agent requests approval via agent.io.request_approval()
    - Client responds to approval requests

    Session support (same as HTTP):
    - Accept session_id in INPUT message for conversation continuation
    - Return session_id and session in OUTPUT message
    """
    if scope["path"] != "/ws":
        # ASGI: close connection with custom code
        await send({"type": "websocket.close", "code": 4004})
        return

    # ASGI: accept the WebSocket connection
    await send({"type": "websocket.accept"})

    # ASGI message loop
    while True:
        msg = await receive()  # ASGI: wait for next message
        if msg["type"] == "websocket.disconnect":  # ASGI: client disconnected
            break
        if msg["type"] == "websocket.receive":  # ASGI: client sent a message
            try:
                data = json.loads(msg.get("text", "{}"))  # Our app data is inside "text"
            except json.JSONDecodeError:
                await send({"type": "websocket.send",  # ASGI: send message to client
                           "text": json.dumps({"type": "ERROR", "message": "Invalid JSON"})})
                continue

            if data.get("type") == "INPUT":  # Our app type: client wants to run agent
                prompt, identity, sig_valid, err = route_handlers["auth"](
                    data, trust, blacklist=blacklist, whitelist=whitelist
                )
                if err:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": err})})
                    continue
                if not prompt:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": "prompt required"})})
                    continue

                # Extract session for conversation continuation (same as HTTP)
                session = data.get("session")

                # Create IO for bidirectional communication
                io = WebSocketIO()
                agent_done = threading.Event()
                result_holder = [None]
                error_holder = [None]

                def run_agent():
                    try:
                        result_holder[0] = route_handlers["ws_input"](storage, prompt, io, session)
                    except Exception as e:
                        error_holder[0] = str(e)
                    agent_done.set()

                # Start agent in thread
                agent_thread = threading.Thread(target=run_agent, daemon=True)
                agent_thread.start()

                # Pump messages between WebSocket and IO
                # TODO: If client disconnects mid-request, result is still saved to SessionStorage.
                # Client could check GET /sessions/{session_id} on reconnect to fetch pending results.
                # For now, we just skip sending if client disconnected.
                client_disconnected = await _pump_messages(receive, send, io, agent_done)

                # Send error or final result (skip if client disconnected)
                if client_disconnected:
                    pass  # Client gone, result saved to storage, nothing to send
                elif error_holder[0]:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": error_holder[0]})})
                elif result_holder[0]:
                    result = result_holder[0]
                    await send({"type": "websocket.send",
                               "text": json.dumps({
                                   "type": "OUTPUT",
                                   "result": result["result"],
                                   "session_id": result["session_id"],
                                   "duration_ms": result["duration_ms"],
                                   "session": result["session"]
                               }, default=pydantic_json_encoder)})
                else:
                    await send({"type": "websocket.send",
                               "text": json.dumps({"type": "ERROR", "message": "Agent completed without result"})})


async def _pump_messages(ws_receive, ws_send, io: WebSocketIO, agent_done: threading.Event) -> bool:
    """Pump messages between WebSocket and IO queues.

    Runs until agent completes. Handles:
    - Outgoing: io._outgoing queue -> WebSocket
    - Incoming: WebSocket -> io._incoming queue (for approval responses)

    Returns:
        True if client disconnected before agent completed, False otherwise.
        When True, caller should skip sending final OUTPUT (client is gone,
        but result is already saved to SessionStorage).

    Implementation note:
        Uses asyncio.Event for signaling disconnect between nested async functions.
        This is preferred over `nonlocal` boolean because:
        - No risk of forgetting `nonlocal` keyword (which would create local var)
        - Clearer intent: Event.set()/is_set() vs boolean reassignment
        - Thread-safe if needed in future
    """
    loop = asyncio.get_event_loop()

    # Signal for client disconnect - shared between send/receive tasks
    # Using Event instead of boolean avoids `nonlocal` complexity
    disconnected = asyncio.Event()

    async def send_outgoing():
        """Send outgoing messages from IO to WebSocket."""
        while not agent_done.is_set() and not disconnected.is_set():
            try:
                event = await loop.run_in_executor(
                    None, lambda: io._outgoing.get(timeout=0.05)
                )
                await ws_send({"type": "websocket.send", "text": json.dumps(event, default=pydantic_json_encoder)})
            except queue.Empty:
                pass

        # Drain remaining messages (only if client still connected)
        if not disconnected.is_set():
            while True:
                try:
                    event = io._outgoing.get_nowait()
                    await ws_send({"type": "websocket.send", "text": json.dumps(event, default=pydantic_json_encoder)})
                except queue.Empty:
                    break

    async def receive_incoming():
        """Receive incoming messages from WebSocket to IO."""
        while not agent_done.is_set():
            try:
                msg = await asyncio.wait_for(ws_receive(), timeout=0.1)
                if msg["type"] == "websocket.receive":
                    try:
                        data = json.loads(msg.get("text", "{}"))
                        io._incoming.put(data)
                    except json.JSONDecodeError:
                        pass
                elif msg["type"] == "websocket.disconnect":
                    disconnected.set()
                    io.close()
                    break
            except asyncio.TimeoutError:
                continue

    send_task = asyncio.create_task(send_outgoing())
    recv_task = asyncio.create_task(receive_incoming())

    while not agent_done.is_set():
        await asyncio.sleep(0.05)

    recv_task.cancel()
    try:
        await recv_task
    except asyncio.CancelledError:
        pass
    await send_task

    return disconnected.is_set()
