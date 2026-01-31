"""
Purpose: Abstract IO interface for bidirectional agent-client communication in hosted agents
LLM-Note:
  Dependencies: imports from [abc.ABC, typing] | imported by [network/io/websocket.py, network/__init__.py, agent.py] | tested by [tests/network/test_io.py]
  Data flow: agent.io.send(event) → client receives event → agent.io.receive() → blocks until client responds | high-level: io.log(type, **data) for one-way notifications | io.request_approval(tool, args) sends approval_needed → waits for client response → returns True/False
  State/Effects: no state (abstract base class) | implementations handle message queuing/transport
  Integration: exposes IO abstract class with send(event), receive() → dict primitives | convenience methods: log(type, **data), request_approval(tool, args) → bool | agent.io injected by host() for hosted execution | used in event handlers (@after_llm, @before_each_tool)
  Performance: abstract (implementation-specific) | WebSocketIO uses queue.Queue for thread-safe communication
  Errors: abstract methods must be implemented by subclasses | request_approval() blocks until response (timeout handled by implementation)
IO interface for agent-client communication during hosted execution.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class IO(ABC):
    """Base IO interface for agent-client communication.

    Two-layer API:
    - Low-level: send(event), receive() - primitives for any communication
    - High-level: log(type, **data), request_approval(tool, args) - common patterns

    Usage in event handlers:
        @after_llm
        def on_thinking(agent):
            if agent.io:
                agent.io.log("thinking")

        @before_each_tool
        def on_tool(agent):
            if agent.io:
                tool = agent.current_session['pending_tool']
                if tool['name'] in DANGEROUS:
                    if not agent.io.request_approval(tool['name'], tool['arguments']):
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
            io.log("thinking")
            io.log("tool_call", name="search", arguments={"q": "python"})
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
            if not io.request_approval("delete_file", {"path": "/tmp/x"}):
                raise ToolRejected()
        """
        self.send({"type": "approval_needed", "tool": tool, "arguments": arguments})
        response = self.receive()
        return response.get("approved", False)
