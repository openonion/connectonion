"""Unit tests for connectonion/tool_executor.py"""

import pytest
from unittest.mock import Mock
from connectonion.tool_executor import execute_single_tool
from connectonion.console import Console


class FakeAgent:
    def __init__(self):
        self.current_session = {"messages": [], "trace": [], "iteration": 1}

    def _invoke_events(self, event_type: str):
        """Stub for event invocation - no-op in test."""
        pass


class TestToolExecutor:
    """Test minimal path of tool execution utility."""

    def test_execute_tool_success(self):
        """Test successful tool execution path via execute_single_tool."""
        def sample_tool(x: int) -> int:
            return x * 2

        agent = FakeAgent()
        console = Console()
        trace = execute_single_tool(
            tool_name="sample_tool",
            tool_args={"x": 5},
            tool_id="call_1",
            tool_map={"sample_tool": sample_tool},
            agent=agent,
            console=console,
        )
        assert trace["status"] == "success"
        # execute_single_tool stores the raw result as string in trace['result']
        assert "10" in str(trace["result"])

    def test_execute_tool_not_found(self):
        """Unknown tool returns not_found status."""
        agent = FakeAgent()
        console = Console()
        trace = execute_single_tool(
            tool_name="missing",
            tool_args={},
            tool_id="call_2",
            tool_map={},
            agent=agent,
            console=console,
        )
        assert trace["status"] == "not_found"
