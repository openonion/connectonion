"""
Purpose: Connection interface for agent-client communication during hosted execution
LLM-Note:
  Dependencies: imports from [abc, typing] | imported by [asgi.py, __init__.py] | tested by [tests/unit/test_connection.py]
  Data flow: receives from host/asgi → WebSocket send/receive → provides log() and request_approval() to agent event handlers
  State/Effects: stateless base class | WebSocketConnection wraps ASGI WebSocket for bidirectional messaging
  Integration: exposes Connection (base), WebSocketConnection (ASGI adapter) | agent.connection set by host() during WebSocket requests
  Performance: log() is fire-and-forget (non-blocking) | request_approval() blocks waiting for client response
  Errors: WebSocketConnection raises if WebSocket closed unexpectedly
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class Connection(ABC):
    """Base connection interface for agent-client communication.

    Two-layer API:
    - Low-level: send(event), receive() - primitives for any communication
    - High-level: log(type, **data), request_approval(tool, args) - common patterns

    Usage in event handlers:
        @after_llm
        def on_thinking(agent):
            if agent.connection:
                agent.connection.log("thinking")

        @before_each_tool
        def on_tool(agent):
            if agent.connection:
                tool = agent.current_session['pending_tool']
                if tool['name'] in DANGEROUS:
                    if not agent.connection.request_approval(tool['name'], tool['arguments']):
                        raise ToolRejected()
    """

    # ═══════════════════════════════════════════════════════
    # LOW-LEVEL API (Primitives)
    # ═══════════════════════════════════════════════════════

    @abstractmethod
    def send(self, event: Dict[str, Any]) -> None:
        """Send any event to client.

        Args:
            event: Dict with at least 'type' key, e.g. {"type": "thinking"}
        """
        pass

    @abstractmethod
    def receive(self) -> Dict[str, Any]:
        """Receive response from client.

        Returns:
            Dict response from client
        """
        pass

    # ═══════════════════════════════════════════════════════
    # HIGH-LEVEL API (Patterns)
    # ═══════════════════════════════════════════════════════

    def log(self, event_type: str, **data) -> None:
        """One-way notification to client.

        Common event types: thinking, tool_call, tool_result, complete, error

        Args:
            event_type: Type of event (e.g. "thinking", "tool_call")
            **data: Additional data for the event

        Example:
            connection.log("thinking")
            connection.log("tool_call", name="search", arguments={"q": "python"})
        """
        self.send({"type": event_type, **data})

    def request_approval(self, tool: str, arguments: Dict[str, Any]) -> bool:
        """Two-way: request permission, wait for response.

        Sends approval_needed event and blocks until client responds.

        Args:
            tool: Name of tool requiring approval
            arguments: Tool arguments to show user

        Returns:
            True if approved, False if rejected

        Example:
            if not connection.request_approval("delete_file", {"path": "/tmp/x"}):
                raise ToolRejected()
        """
        self.send({"type": "approval_needed", "tool": tool, "arguments": arguments})
        response = self.receive()
        return response.get("approved", False)


class SyncWebSocketConnection(Connection):
    """Synchronous WebSocket connection adapter.

    Wraps async WebSocket send/receive for use in synchronous agent code.
    Uses threading events to bridge async/sync boundary.
    """

    def __init__(self, send_callback, receive_callback):
        """Initialize with send/receive callbacks.

        Args:
            send_callback: Callable that sends message to WebSocket
            receive_callback: Callable that receives message from WebSocket
        """
        self._send = send_callback
        self._receive = receive_callback

    def send(self, event: Dict[str, Any]) -> None:
        """Send event to client via WebSocket."""
        self._send(event)

    def receive(self) -> Dict[str, Any]:
        """Receive response from client via WebSocket."""
        return self._receive()
