"""Unit tests for on_tool_not_found event.

Tests cover:
- on_tool_not_found fires when tool is missing
- handler return value overrides default error message
- handler returning None uses default error message
- multiple handlers: first non-None return wins
- pending_tool set in session before event fires
- pending_tool cleared from session after event
- event exported from connectonion package
"""
"""
LLM-Note: Tests for on_tool_not_found event

What it tests:
- on_tool_not_found event lifecycle

Components under test:
- Module: tool_executor (execute_single_tool)
- Module: events (on_tool_not_found)
- Module: agent (_invoke_events_with_return)
"""

import pytest
from connectonion.core.tool_executor import execute_single_tool
from connectonion.core.tool_registry import ToolRegistry
from connectonion.logger import Logger
from connectonion import on_tool_not_found


class FakeAgent:
    def __init__(self, handlers=None):
        self.name = "test-agent"
        self.current_session = {"messages": [], "trace": [], "iteration": 1}
        self.connection = None
        self.io = None
        self._trace_id = 0
        self._handlers = handlers or []

    def _next_trace_id(self):
        self._trace_id += 1
        return self._trace_id

    def _record_trace(self, entry: dict):
        if 'id' not in entry:
            entry['id'] = self._next_trace_id()
        self.current_session['trace'].append(entry)

    def _invoke_events(self, event_type: str):
        pass

    def _invoke_events_with_return(self, event_type: str):
        result = None
        for handler_type, handler in self._handlers:
            if handler_type == event_type:
                ret = handler(self)
                if ret is not None and result is None:
                    result = ret
        return result


class TestOnToolNotFoundEvent:
    """Test on_tool_not_found fires when tool is missing."""

    def test_fires_when_tool_missing(self):
        """on_tool_not_found handler should be called for missing tool."""
        called_with = []

        def handler(agent):
            called_with.append(agent.current_session.get('pending_tool'))

        agent = FakeAgent(handlers=[('on_tool_not_found', handler)])
        tools = ToolRegistry()
        logger = Logger("test", log=False)

        execute_single_tool("nonexistent_tool", {}, "call_1", tools, agent, logger)

        assert len(called_with) == 1
        assert called_with[0]['name'] == 'nonexistent_tool'

    def test_does_not_fire_for_existing_tool(self):
        """on_tool_not_found should NOT fire when tool exists."""
        called = []

        def handler(agent):
            called.append(True)

        def my_tool() -> str:
            return "ok"

        from connectonion.core.tool_factory import create_tool_from_function
        tools = ToolRegistry()
        tools.add(create_tool_from_function(my_tool))
        agent = FakeAgent(handlers=[('on_tool_not_found', handler)])
        logger = Logger("test", log=False)

        execute_single_tool("my_tool", {}, "call_1", tools, agent, logger)

        assert len(called) == 0


class TestCustomErrorMessage:
    """Test handler return value overrides default error message."""

    def test_handler_return_overrides_default(self):
        """Handler returning a string should use it as the error message."""
        def handler(agent):
            return "Custom: tool not found, try 'search' instead"

        agent = FakeAgent(handlers=[('on_tool_not_found', handler)])
        tools = ToolRegistry()
        logger = Logger("test", log=False)

        trace = execute_single_tool("missing_tool", {}, "call_1", tools, agent, logger)

        assert trace["result"] == "Custom: tool not found, try 'search' instead"
        assert trace["error"] == "Custom: tool not found, try 'search' instead"

    def test_handler_returning_none_uses_default(self):
        """Handler returning None should fall back to default error message."""
        def handler(agent):
            return None

        agent = FakeAgent(handlers=[('on_tool_not_found', handler)])
        tools = ToolRegistry()
        logger = Logger("test", log=False)

        trace = execute_single_tool("missing_tool", {}, "call_1", tools, agent, logger)

        assert trace["result"] == "Tool 'missing_tool' not found"

    def test_no_handler_uses_default_message(self):
        """Without handlers, default error message should be used."""
        agent = FakeAgent()
        tools = ToolRegistry()
        logger = Logger("test", log=False)

        trace = execute_single_tool("unknown_tool", {}, "call_1", tools, agent, logger)

        assert trace["result"] == "Tool 'unknown_tool' not found"
        assert trace["status"] == "not_found"

    def test_first_non_none_handler_wins(self):
        """When multiple handlers, first non-None return should be used."""
        def handler_none(agent):
            return None

        def handler_first(agent):
            return "First handler message"

        def handler_second(agent):
            return "Second handler message"

        agent = FakeAgent(handlers=[
            ('on_tool_not_found', handler_none),
            ('on_tool_not_found', handler_first),
            ('on_tool_not_found', handler_second),
        ])
        tools = ToolRegistry()
        logger = Logger("test", log=False)

        trace = execute_single_tool("missing_tool", {}, "call_1", tools, agent, logger)

        assert trace["result"] == "First handler message"


class TestPendingToolInSession:
    """Test pending_tool is set and cleared correctly."""

    def test_pending_tool_available_during_handler(self):
        """pending_tool should be set in session when handler fires."""
        captured = {}

        def handler(agent):
            captured.update(agent.current_session.get('pending_tool', {}))

        agent = FakeAgent(handlers=[('on_tool_not_found', handler)])
        tools = ToolRegistry()
        logger = Logger("test", log=False)

        execute_single_tool("missing_tool", {"arg": "val"}, "call_99", tools, agent, logger)

        assert captured['name'] == 'missing_tool'
        assert captured['arguments'] == {"arg": "val"}
        assert captured['id'] == 'call_99'

    def test_pending_tool_cleared_after_handler(self):
        """pending_tool should be removed from session after handler completes."""
        agent = FakeAgent()
        tools = ToolRegistry()
        logger = Logger("test", log=False)

        execute_single_tool("missing_tool", {}, "call_1", tools, agent, logger)

        assert 'pending_tool' not in agent.current_session

    def test_trace_status_is_not_found(self):
        """Trace entry status should be 'not_found' for missing tools."""
        agent = FakeAgent()
        tools = ToolRegistry()
        logger = Logger("test", log=False)

        trace = execute_single_tool("missing_tool", {}, "call_1", tools, agent, logger)

        assert trace["status"] == "not_found"
        assert "missing_tool" in trace["error"]


class TestEventWrapper:
    """Test on_tool_not_found wrapper in events module."""

    def test_decorator_sets_event_type(self):
        """@on_tool_not_found decorator should set _event_type attribute."""
        @on_tool_not_found
        def my_handler(agent):
            pass

        assert my_handler._event_type == 'on_tool_not_found'

    def test_wrapper_syntax_sets_event_type(self):
        """on_tool_not_found(fn) wrapper syntax should set _event_type."""
        def my_handler(agent):
            pass

        wrapped = on_tool_not_found(my_handler)
        assert wrapped._event_type == 'on_tool_not_found'

    def test_multiple_handlers_returns_list(self):
        """on_tool_not_found(fn1, fn2) should return a list."""
        def h1(agent): pass
        def h2(agent): pass

        result = on_tool_not_found(h1, h2)
        assert isinstance(result, list)
        assert len(result) == 2
        assert all(h._event_type == 'on_tool_not_found' for h in result)


class TestAgentIntegration:
    """Test on_tool_not_found integrates with real Agent."""

    def test_agent_registers_event(self):
        """Agent should accept on_tool_not_found handlers via on_events."""
        from connectonion import Agent
        from unittest.mock import Mock
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="done",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        @on_tool_not_found
        def my_handler(agent) -> str:
            return "handled"

        agent = Agent("test", llm=mock_llm, on_events=[my_handler], log=False)

        assert 'on_tool_not_found' in agent.events
        assert len(agent.events['on_tool_not_found']) == 1

    def test_invoke_events_with_return_returns_first_non_none(self):
        """_invoke_events_with_return should return first non-None handler result."""
        from connectonion import Agent
        from unittest.mock import Mock
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="done",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        @on_tool_not_found
        def returns_none(agent):
            return None

        @on_tool_not_found
        def returns_msg(agent):
            return "custom error"

        agent = Agent("test", llm=mock_llm, on_events=[returns_none, returns_msg], log=False)
        result = agent._invoke_events_with_return('on_tool_not_found')

        assert result == "custom error"

    def test_invoke_events_with_return_all_none_returns_none(self):
        """_invoke_events_with_return should return None when all handlers return None."""
        from connectonion import Agent
        from unittest.mock import Mock
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="done",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        @on_tool_not_found
        def returns_none(agent):
            return None

        agent = Agent("test", llm=mock_llm, on_events=[returns_none], log=False)
        result = agent._invoke_events_with_return('on_tool_not_found')

        assert result is None
