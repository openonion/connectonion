"""
Purpose: IO module re-exporting base IO protocol and WebSocket implementation
LLM-Note:
  Dependencies: imports from [base.py, websocket.py] | imported by [network/__init__.py, agent.py, network/asgi/websocket.py] | tested by [tests/network/test_io.py]
  Data flow: re-exports IO abstract class and WebSocketIO concrete implementation
  State/Effects: no state
  Integration: exposes IO(ABC) protocol with send(event), receive() → dict, log(type, **data), request_approval(tool, args) → bool | WebSocketIO uses queue-based async-to-sync bridge for agent.io attribute
  Performance: trivial
  Errors: none
IO module for agent-client communication.

Provides the IO interface and WebSocket implementation.
"""

from .base import IO
from .websocket import WebSocketIO

__all__ = [
    "IO",
    "WebSocketIO",
]
