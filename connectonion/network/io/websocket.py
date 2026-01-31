"""
Purpose: WebSocket IO implementation bridging async WebSocket to sync agent code via queues
LLM-Note:
  Dependencies: imports from [network/io/base.py IO, queue, time, uuid, typing] | imported by [network/asgi/websocket.py, network/host/server.py] | tested by [tests/network/test_websocket_io.py]
  Data flow: agent calls io.send(event) → auto-adds id (UUID) and ts if missing → puts in _outgoing queue → async handler gets via queue.get() → sends via WebSocket | client sends message → async handler puts in _incoming queue → agent blocks on io.receive() → gets from _incoming | close() unblocks waiting receive() with io_closed event
  State/Effects: maintains _outgoing and _incoming queues (thread-safe) | _closed flag prevents sending after close | receive() blocks until message available | auto-generates UUID for events without id (for frontend React keys)
  Integration: exposes WebSocketIO() implementing IO interface | send(event) queues outgoing message with auto-id, receive() → dict blocks for incoming message, close() marks closed | used by handle_websocket() to provide agent.io for bidirectional communication
  Performance: queue-based (thread-safe, no locks needed) | blocking receive() (use in agent thread) | async handler pumps messages between WebSocket and queues
  Errors: closed IO puts io_closed sentinel in _incoming to unblock receive() | no exceptions (queue handles thread coordination)
WebSocket IO implementation.
"""

import queue
import time
import uuid
from typing import Any, Dict

from .base import IO


class WebSocketIO(IO):
    """Bridge async WebSocket to sync IO interface.

    Uses queues to communicate between async WebSocket handler and sync agent code.
    The agent runs in a thread, sending/receiving via queues.
    The async handler pumps messages between WebSocket and queues.
    """

    def __init__(self):
        self._outgoing: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._incoming: queue.Queue[Dict[str, Any]] = queue.Queue()
        self._closed = False

    def send(self, event: Dict[str, Any]) -> None:
        """Queue event to be sent to client.

        Auto-generates 'id' (UUID) and 'ts' (timestamp) if not present,
        ensuring all events have unique IDs for frontend React keys.
        """
        if not self._closed:
            if 'id' not in event:
                event['id'] = str(uuid.uuid4())
            if 'ts' not in event:
                event['ts'] = time.time()
            self._outgoing.put(event)

    def receive(self) -> Dict[str, Any]:
        """Block until response from client."""
        return self._incoming.get()

    def close(self):
        """Mark IO as closed."""
        self._closed = True
        # Unblock any waiting receive
        self._incoming.put({"type": "io_closed"})
