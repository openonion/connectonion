"""Unit tests for connectonion/tool_executor.py"""
"""
LLM-Note: Tests for tool executor

What it tests:
- Tool Executor functionality

Components under test:
- Module: tool_executor
"""


import pytest
from unittest.mock import Mock, patch
from connectonion.core.tool_executor import execute_and_record_tools, execute_single_tool, _add_assistant_message
from connectonion.core.interrupt import AgentInterrupted
from connectonion.core.tool_registry import ToolRegistry
from connectonion.core.tool_factory import create_tool_from_function
from connectonion.logger import Logger
from connectonion.core.llm import ToolCall


class FakeAgent:
    def __init__(self):
        self.name = "test-agent"
        self.current_session = {"messages": [], "trace": [], "iteration": 1}
        self.connection = None
        self.io = None
        self._trace_id = 0

    def _next_trace_id(self):
        self._trace_id += 1
        return self._trace_id

    def _record_trace(self, entry: dict):
        """Record trace entry - mirrors Agent._record_trace."""
        if 'id' not in entry:
            entry['id'] = self._next_trace_id()
        self.current_session['trace'].append(entry)

    def _invoke_events(self, event_type: str):
        """Stub for event invocation - no-op in test."""
        pass


class TestToolExecutor:
    """Test minimal path of tool execution utility."""

    def test_execute_tool_success(self):
        """Test successful tool execution path via execute_single_tool."""
        def sample_tool(x: int) -> int:
            return x * 2

        tools = ToolRegistry()
        tools.add(create_tool_from_function(sample_tool))

        agent = FakeAgent()
        logger = Logger("test-agent", log=False)
        trace = execute_single_tool(
            tool_name="sample_tool",
            tool_args={"x": 5},
            tool_id="call_1",
            tools=tools,
            agent=agent,
            logger=logger,
        )
        assert trace["status"] == "success"
        # execute_single_tool stores the raw result as string in trace['result']
        assert "10" in str(trace["result"])

    def test_execute_tool_not_found(self):
        """Unknown tool returns not_found status."""
        tools = ToolRegistry()
        agent = FakeAgent()
        logger = Logger("test-agent", log=False)
        trace = execute_single_tool(
            tool_name="missing",
            tool_args={},
            tool_id="call_2",
            tools=tools,
            agent=agent,
            logger=logger,
        )
        assert trace["status"] == "not_found"

    def test_before_tool_interrupt_clears_pending_tool(self):
        def sample_tool() -> str:
            return "must not run"

        tools = ToolRegistry()
        tools.add(create_tool_from_function(sample_tool))
        agent = FakeAgent()

        def interrupt(event_type):
            if event_type == "before_each_tool":
                raise AgentInterrupted()

        agent._invoke_events = interrupt
        trace = execute_single_tool(
            tool_name="sample_tool",
            tool_args={},
            tool_id="call_interrupt",
            tools=tools,
            agent=agent,
            logger=Logger("test-agent", log=False),
        )

        assert trace["status"] == "interrupted"
        assert "pending_tool" not in agent.current_session

    def test_interrupt_abandons_tool_and_completes_batch_messages(self):
        import threading
        import time

        from connectonion.network.io import WebSocketIO

        started = threading.Event()
        release = threading.Event()
        later_called = False

        def slow_tool() -> str:
            started.set()
            release.wait(timeout=2)
            return "late result"

        def later_tool() -> str:
            nonlocal later_called
            later_called = True
            return "should not run"

        tools = ToolRegistry()
        tools.add(create_tool_from_function(slow_tool))
        tools.add(create_tool_from_function(later_tool))
        agent = FakeAgent()
        agent.io = WebSocketIO()
        logger = Logger("test-agent", log=False)
        calls = [
            ToolCall(
                name="slow_tool",
                arguments={},
                id="call_1",
                extra_content={"google": {"thought_signature": "sig"}},
            ),
            ToolCall(name="later_tool", arguments={}, id="call_2"),
        ]
        sender = threading.Thread(
            target=lambda: (started.wait(timeout=1), agent.io.send_to_agent({"type": "INTERRUPT"})),
            daemon=True,
        )
        sender.start()
        began = time.monotonic()

        execute_and_record_tools(calls, tools, agent, logger)

        assert time.monotonic() - began < 0.8
        assert later_called is False
        assert agent.current_session['messages'][0]['tool_calls'][0]['extra_content'] == {
            "google": {"thought_signature": "sig"}
        }
        results = agent.current_session['messages'][1:]
        assert [(m['tool_call_id'], m['content']) for m in results] == [
            ('call_1', 'Interrupted by user'),
            ('call_2', 'Rejected by user'),
        ]
        terminal = [t for t in agent.current_session['trace'] if t['type'] == 'tool_result'][-1]
        assert terminal['status'] == 'interrupted'
        snapshot = list(agent.current_session['trace'])
        release.set()
        time.sleep(0.02)
        assert agent.current_session['trace'] == snapshot

    def test_interrupt_between_tools_prevents_next_tool_from_starting(self):
        from connectonion.network.io import WebSocketIO

        agent = FakeAgent()
        agent.io = WebSocketIO()
        second_called = False
        third_called = False

        def first_tool() -> str:
            agent.io.send_to_agent({"type": "INTERRUPT"})
            return "first done"

        def second_tool() -> str:
            nonlocal second_called
            second_called = True
            return "second done"

        def third_tool() -> str:
            nonlocal third_called
            third_called = True
            return "third done"

        tools = ToolRegistry()
        for tool in (first_tool, second_tool, third_tool):
            tools.add(create_tool_from_function(tool))
        calls = [
            ToolCall(name="first_tool", arguments={}, id="call_1"),
            ToolCall(name="second_tool", arguments={}, id="call_2"),
            ToolCall(name="third_tool", arguments={}, id="call_3"),
        ]

        execute_and_record_tools(calls, tools, agent, Logger("test-agent", log=False))

        assert second_called is False
        assert third_called is False
        results = agent.current_session['messages'][1:]
        assert [(m['tool_call_id'], m['content']) for m in results] == [
            ('call_1', 'first done'),
            ('call_2', 'Interrupted by user'),
            ('call_3', 'Rejected by user'),
        ]

    def test_abandoned_worker_keeps_its_xray_context_during_next_tool(self):
        import builtins
        import threading

        from connectonion.network.io import WebSocketIO

        started = threading.Event()
        release = threading.Event()
        abandoned_done = threading.Event()
        observed = {}

        def slow_tool() -> str:
            observed["slow_before"] = builtins.xray.task
            started.set()
            release.wait(timeout=2)
            observed["slow_after"] = builtins.xray.task
            abandoned_done.set()
            return "late"

        def next_tool() -> str:
            observed["next"] = builtins.xray.task
            return "next"

        tools = ToolRegistry()
        tools.add(create_tool_from_function(slow_tool))
        tools.add(create_tool_from_function(next_tool))
        agent = FakeAgent()
        agent.io = WebSocketIO()
        agent.current_session["user_prompt"] = "first turn"
        sender = threading.Thread(
            target=lambda: (started.wait(timeout=1), agent.io.send_to_agent({"type": "INTERRUPT"})),
            daemon=True,
        )
        sender.start()

        first = execute_single_tool(
            "slow_tool", {}, "slow", tools, agent, Logger("test-agent", log=False)
        )
        assert first["status"] == "interrupted"

        agent.current_session.pop("stop_signal", None)
        agent.current_session["user_prompt"] = "second turn"
        second = execute_single_tool(
            "next_tool", {}, "next", tools, agent, Logger("test-agent", log=False)
        )
        assert second["status"] == "success"

        release.set()
        assert abandoned_done.wait(timeout=1)
        assert observed == {
            "slow_before": "first turn",
            "next": "second turn",
            "slow_after": "first turn",
        }


class TestAddAssistantMessage:
    """Tests for _add_assistant_message null handling (Gemini compatibility)."""

    def test_excludes_extra_content_when_none(self):
        """extra_content field should NOT be included when it's None.

        Gemini API rejects null values where it expects structs.
        See: https://discuss.ai.google.dev/t/openai-compatibility-api-does-not-support-message-refusal-field-set-to-null/100010
        """
        messages = []
        tool_calls = [
            ToolCall(
                name="test_tool",
                arguments={"x": 1},
                id="call_1",
                extra_content=None  # No extra content
            )
        ]

        _add_assistant_message(messages, tool_calls)

        assert len(messages) == 1
        assistant_msg = messages[0]
        assert assistant_msg["role"] == "assistant"
        assert "tool_calls" in assistant_msg

        # Verify extra_content is NOT in the tool call when None
        tc = assistant_msg["tool_calls"][0]
        assert "extra_content" not in tc
        assert tc["id"] == "call_1"
        assert tc["function"]["name"] == "test_tool"

    def test_includes_extra_content_when_present(self):
        """extra_content field should be included when it has a value.

        This is required for Gemini 3 thought_signature to be echoed back.
        See: https://ai.google.dev/gemini-api/docs/thinking#openai-sdk
        """
        messages = []
        thought_sig = {"signature": "abc123", "type": "thought"}
        tool_calls = [
            ToolCall(
                name="test_tool",
                arguments={"x": 1},
                id="call_1",
                extra_content=thought_sig
            )
        ]

        _add_assistant_message(messages, tool_calls)

        tc = messages[0]["tool_calls"][0]
        assert "extra_content" in tc
        assert tc["extra_content"] == thought_sig

    def test_assistant_message_no_content_field(self):
        """Assistant message with tool_calls should not have content field.

        Gemini rejects null content values. Omitting the field is safer.
        """
        messages = []
        tool_calls = [
            ToolCall(name="test", arguments={}, id="call_1", extra_content=None)
        ]

        _add_assistant_message(messages, tool_calls)

        assistant_msg = messages[0]
        # content key should not be present (or if present, not None)
        assert "content" not in assistant_msg or assistant_msg.get("content") is not None


class TestLoggerIntegration:
    """Tests for logger integration in tool executor."""

    def test_log_tool_call_invoked_before_execution(self):
        """Logger.log_tool_call is called before tool execution."""
        def sample_tool(x: int) -> int:
            return x * 2

        tools = ToolRegistry()
        tools.add(create_tool_from_function(sample_tool))

        agent = FakeAgent()
        logger = Mock()

        execute_single_tool(
            tool_name="sample_tool",
            tool_args={"x": 5},
            tool_id="call_1",
            tools=tools,
            agent=agent,
            logger=logger,
        )

        # Verify log_tool_call was called with correct args
        logger.log_tool_call.assert_called_once_with("sample_tool", {"x": 5})

    def test_log_tool_result_invoked_after_success(self):
        """Logger.log_tool_result is called after successful execution."""
        def sample_tool(x: int) -> int:
            return x * 2

        tools = ToolRegistry()
        tools.add(create_tool_from_function(sample_tool))

        agent = FakeAgent()
        logger = Mock()

        execute_single_tool(
            tool_name="sample_tool",
            tool_args={"x": 5},
            tool_id="call_1",
            tools=tools,
            agent=agent,
            logger=logger,
        )

        # Verify log_tool_result was called with result and timing
        logger.log_tool_result.assert_called_once()
        args, kwargs = logger.log_tool_result.call_args
        assert args[0] == "10"  # Result as string
        assert isinstance(args[1], float)  # Timing in ms
        assert args[1] >= 0  # Non-negative timing

    def test_log_tool_call_invoked_for_not_found(self):
        """Logger.log_tool_call is called even when tool not found."""
        tools = ToolRegistry()
        agent = FakeAgent()
        logger = Mock()

        execute_single_tool(
            tool_name="missing_tool",
            tool_args={"x": 1},
            tool_id="call_1",
            tools=tools,
            agent=agent,
            logger=logger,
        )

        # log_tool_call still called
        logger.log_tool_call.assert_called_once_with("missing_tool", {"x": 1})
        # log_tool_result NOT called for not_found
        logger.log_tool_result.assert_not_called()
        # Error message printed
        logger.print.assert_called_once()
        assert "not found" in logger.print.call_args[0][0]

    def test_logger_print_called_on_error(self):
        """Logger.print is called with error message when tool raises."""
        def failing_tool() -> str:
            raise ValueError("Something went wrong")

        tools = ToolRegistry()
        tools.add(create_tool_from_function(failing_tool))

        agent = FakeAgent()
        logger = Mock()

        trace = execute_single_tool(
            tool_name="failing_tool",
            tool_args={},
            tool_id="call_1",
            tools=tools,
            agent=agent,
            logger=logger,
        )

        # Verify error handling
        assert trace["status"] == "error"
        logger.log_tool_call.assert_called_once()
        logger.print.assert_called_once()
        error_output = logger.print.call_args[0][0]
        assert "Error" in error_output or "✗" in error_output
        assert "Something went wrong" in error_output

    def test_error_includes_schema_info(self):
        """Error result includes tool schema so LLM can fix the call."""
        def write_file(path: str, content: str) -> str:
            """Write content to file."""
            return f"wrote {len(content)} bytes"

        tools = ToolRegistry()
        tools.add(create_tool_from_function(write_file))

        agent = FakeAgent()
        logger = Mock()

        # Call with missing required argument
        trace = execute_single_tool(
            tool_name="write_file",
            tool_args={"path": "/tmp/test.py"},  # Missing 'content'!
            tool_id="call_1",
            tools=tools,
            agent=agent,
            logger=logger,
        )

        # Verify error includes schema info
        assert trace["status"] == "error"
        result = trace["result"]
        assert "required=" in result
        assert "path" in result
        assert "content" in result
        assert "you_provided=" in result
