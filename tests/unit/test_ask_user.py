"""Unit tests for ask_user tool."""

import pytest
from unittest.mock import Mock
from connectonion.useful_tools.ask_user import ask_user
from connectonion.core.tool_factory import create_tool_from_function
from connectonion.core.tool_executor import execute_single_tool
from connectonion.core.tool_registry import ToolRegistry
from connectonion.logger import Logger


class FakeAgent:
    """Minimal agent for testing."""

    def __init__(self):
        self.name = "test-agent"
        self.current_session = {"messages": [], "trace": [], "iteration": 1}
        self.io = None
        self._trace_id = 0

    def _next_trace_id(self):
        self._trace_id += 1
        return self._trace_id

    def _record_trace(self, entry):
        """Record trace entry (simplified for testing)."""
        import time
        if 'id' not in entry:
            entry['id'] = self._next_trace_id()
        if 'ts' not in entry:
            entry['ts'] = time.time()
        self.current_session['trace'].append(entry)
        if self.io:
            self.io.send(entry)

    def _invoke_events(self, event_type: str):
        pass


class TestAskUserTool:
    """Test ask_user tool function."""

    def test_ask_user_sends_event_and_receives_answer(self):
        """ask_user sends event via connection and returns answer."""
        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive.return_value = {"answer": "blue"}

        result = ask_user(agent, "What color?", options=["red", "blue"])

        agent.io.send.assert_called_once_with({
            "type": "ask_user",
            "question": "What color?",
            "options": ["red", "blue"],
            "multi_select": False
        })
        agent.io.receive.assert_called_once()
        assert result == "blue"

    def test_ask_user_with_multi_select(self):
        """ask_user sends multi_select flag."""
        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive.return_value = {"answer": "python,rust"}

        result = ask_user(
            agent,
            "Which languages?",
            options=["python", "rust", "go"],
            multi_select=True
        )

        agent.io.send.assert_called_once_with({
            "type": "ask_user",
            "question": "Which languages?",
            "options": ["python", "rust", "go"],
            "multi_select": True
        })
        assert result == "python,rust"

    def test_ask_user_with_empty_options(self):
        """ask_user works with empty options list."""
        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive.return_value = {"answer": "my-project"}

        result = ask_user(agent, "Project name?", options=[])

        agent.io.send.assert_called_once_with({
            "type": "ask_user",
            "question": "Project name?",
            "options": [],
            "multi_select": False
        })
        assert result == "my-project"

    def test_ask_user_empty_answer(self):
        """ask_user returns empty string if no answer in response."""
        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive.return_value = {}

        result = ask_user(agent, "Question?", options=["A", "B"])

        assert result == ""


class TestAskUserSchema:
    """Test that ask_user schema excludes agent parameter."""

    def test_agent_not_in_schema(self):
        """agent parameter should not appear in tool schema."""
        tool = create_tool_from_function(ask_user)
        schema = tool.to_function_schema()

        assert "agent" not in schema["parameters"]["properties"]
        assert "question" in schema["parameters"]["properties"]
        assert "options" in schema["parameters"]["properties"]
        assert "multi_select" in schema["parameters"]["properties"]

    def test_question_and_options_are_required(self):
        """question and options should be required."""
        tool = create_tool_from_function(ask_user)
        schema = tool.to_function_schema()

        assert "question" in schema["parameters"]["required"]
        assert "options" in schema["parameters"]["required"]
        assert "multi_select" not in schema["parameters"].get("required", [])


class TestAskUserInjection:
    """Test that tool_executor injects agent for tools with 'agent' in signature."""

    def test_agent_injected_for_ask_user(self):
        """tool_executor injects agent when tool declares 'agent' in signature."""
        tools = ToolRegistry()
        tools.add(create_tool_from_function(ask_user))

        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive.return_value = {"answer": "test"}

        logger = Logger("test", log=False)

        trace = execute_single_tool(
            tool_name="ask_user",
            tool_args={"question": "Test?", "options": ["A", "B"]},
            tool_id="call_1",
            tools=tools,
            agent=agent,
            logger=logger,
        )

        assert trace["status"] == "success"
        assert trace["result"] == "test"
        # io.send is called 3 times:
        # 1. tool_call event (before execution)
        # 2. ask_user event (during ask_user tool execution)
        # 3. tool_result event (after execution)
        assert agent.io.send.call_count == 3
        # First call should be the tool_call event
        first_call = agent.io.send.call_args_list[0]
        assert first_call[0][0]["type"] == "tool_call"
        # Second call should be the ask_user event
        second_call = agent.io.send.call_args_list[1]
        assert second_call[0][0]["type"] == "ask_user"

    def test_agent_not_injected_for_other_tools(self):
        """tool_executor does not inject agent for regular tools."""
        def regular_tool(x: int) -> int:
            return x * 2

        tools = ToolRegistry()
        tools.add(create_tool_from_function(regular_tool))

        agent = FakeAgent()
        logger = Logger("test", log=False)

        trace = execute_single_tool(
            tool_name="regular_tool",
            tool_args={"x": 5},
            tool_id="call_1",
            tools=tools,
            agent=agent,
            logger=logger,
        )

        assert trace["status"] == "success"
        assert trace["result"] == "10"
