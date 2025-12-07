#!/usr/bin/env python3
"""
Unit tests for tool_executor.py error handling.

Tests cover:
- Tool not found errors
- Tool execution exceptions (various types)
- Xray context injection/clearing on errors
- Event invocation (on_error events)
- Trace entry structure for errors
- Timing measurements on errors
- Message formatting with errors

Critical error paths from coverage analysis:
- execute_single_tool() exception handling (line 180-202)
- Tool not found handling (line 108-119)
- Xray context cleanup in finally block (line 203-205)
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from connectonion.tool_executor import (
    execute_and_record_tools,
    execute_single_tool,
    _add_assistant_message,
    _add_tool_result_message
)
from connectonion.llm import ToolCall
from connectonion.logger import Logger


class TestToolNotFound:
    """Test handling when tool doesn't exist in tools registry."""

    def test_tool_not_found_creates_error_trace(self):
        """Test that non-existent tool creates not_found trace entry."""
        # Setup - use dict as mock (has get() method)
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        logger = Logger("test", log=False)
        tools = {"existing_tool": lambda x: "result"}

        # Execute non-existent tool
        trace_entry = execute_single_tool(
            tool_name="nonexistent_tool",
            tool_args={"param": "value"},
            tool_id="call_123",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify trace entry structure
        assert trace_entry["type"] == "tool_execution"
        assert trace_entry["tool_name"] == "nonexistent_tool"
        assert trace_entry["status"] == "not_found"
        assert "not found" in trace_entry["error"]
        assert "not found" in trace_entry["result"]
        assert trace_entry["call_id"] == "call_123"

    def test_tool_not_found_does_not_execute(self):
        """Test that non-existent tool doesn't execute any function."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        logger = Logger("test", log=False)

        # Tool that should never be called
        mock_tool = Mock(return_value="should not see this")
        tools = {"other_tool": mock_tool}

        # Execute non-existent tool
        trace_entry = execute_single_tool(
            tool_name="missing_tool",
            tool_args={},
            tool_id="call_xyz",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify mock tool was never called
        mock_tool.assert_not_called()
        assert trace_entry["status"] == "not_found"

    def test_tool_not_found_in_execute_and_record(self):
        """Test tool not found in full execute_and_record_tools flow."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)
        tools = {"calc": lambda x: x * 2}

        tool_calls = [
            ToolCall(name="unknown_tool", arguments={"x": 5}, id="call_1")
        ]

        execute_and_record_tools(tool_calls, tools, mock_agent, logger)

        # Verify messages were added
        assert len(mock_agent.current_session['messages']) == 2  # assistant + tool result
        # Verify tool result contains error
        tool_result_msg = mock_agent.current_session['messages'][1]
        assert tool_result_msg["role"] == "tool"
        assert "not found" in tool_result_msg["content"]


class TestToolExecutionExceptions:
    """Test handling of exceptions during tool execution."""

    def test_tool_exception_creates_error_trace(self):
        """Test that tool exceptions are captured in trace with error details."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 2
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def failing_tool(x):
            raise ValueError("Invalid input value")

        tools = {"failing_tool": failing_tool}

        trace_entry = execute_single_tool(
            tool_name="failing_tool",
            tool_args={"x": "bad"},
            tool_id="call_456",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify error trace structure
        assert trace_entry["status"] == "error"
        assert trace_entry["error"] == "Invalid input value"
        assert trace_entry["error_type"] == "ValueError"
        assert "Error executing tool" in trace_entry["result"]
        assert trace_entry["timing"] > 0  # Should still record timing

    def test_tool_exception_invokes_on_error_event(self):
        """Test that on_error events are invoked when tool fails."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def crashing_tool():
            raise RuntimeError("Tool crashed!")

        tools = {"crash": crashing_tool}

        tool_calls = [ToolCall(id="call_789", name="crash", arguments={})]

        execute_and_record_tools(
            tool_calls=tool_calls,
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify on_error event was invoked
        mock_agent._invoke_events.assert_any_call('on_error')

    def test_various_exception_types_captured(self):
        """Test that different exception types are all captured correctly."""
        mock_agent = Mock()
        mock_agent._invoke_events = Mock()
        logger = Logger("test", log=False)

        # Test different exception types
        exceptions_to_test = [
            (TypeError, "Type error message"),
            (KeyError, "missing_key"),
            (AttributeError, "no such attribute"),
            (ZeroDivisionError, "division by zero"),
            (IOError, "file not found"),
        ]

        for exc_type, exc_msg in exceptions_to_test:
            mock_agent.current_session = {
                'messages': [],
                'trace': [],
                'iteration': 1
            }

            def failing_tool():
                raise exc_type(exc_msg)

            tools = {"test": failing_tool}

            trace_entry = execute_single_tool(
                tool_name="test",
                tool_args={},
                tool_id="call_test",
                tools=tools,
                agent=mock_agent,
                logger=logger
            )

            assert trace_entry["status"] == "error"
            assert trace_entry["error_type"] == exc_type.__name__
            assert str(exc_msg) in trace_entry["error"] or trace_entry["error"] == str(exc_msg)

    def test_tool_error_still_records_timing(self):
        """Test that timing is recorded even when tool fails."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def slow_failing_tool():
            time.sleep(0.01)  # Sleep 10ms
            raise Exception("Delayed failure")

        tools = {"slow_fail": slow_failing_tool}

        trace_entry = execute_single_tool(
            tool_name="slow_fail",
            tool_args={},
            tool_id="call_slow",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Timing should be at least 10ms
        assert trace_entry["timing"] >= 10.0
        assert trace_entry["status"] == "error"

    def test_tool_error_added_to_session_trace(self):
        """Test that error trace entries are added to session."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def error_tool():
            raise ValueError("Test error")

        tools = {"error": error_tool}

        execute_single_tool(
            tool_name="error",
            tool_args={},
            tool_id="call_err",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify trace entry was added to session
        assert len(mock_agent.current_session['trace']) == 1
        trace_entry = mock_agent.current_session['trace'][0]
        assert trace_entry["status"] == "error"
        assert trace_entry["error"] == "Test error"


class TestXrayContextHandling:
    """Test xray context injection and cleanup on errors."""

    @patch('connectonion.tool_executor.inject_xray_context')
    @patch('connectonion.tool_executor.clear_xray_context')
    def test_xray_context_cleared_on_success(self, mock_clear, mock_inject):
        """Test that xray context is cleared after successful tool execution."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1,
            'user_prompt': 'test'
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def success_tool():
            return "success"

        tools = {"success": success_tool}

        execute_single_tool(
            tool_name="success",
            tool_args={},
            tool_id="call_ok",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify context was injected and cleared
        mock_inject.assert_called_once()
        mock_clear.assert_called_once()

    @patch('connectonion.tool_executor.inject_xray_context')
    @patch('connectonion.tool_executor.clear_xray_context')
    def test_xray_context_cleared_on_error(self, mock_clear, mock_inject):
        """Test that xray context is cleared even when tool fails."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1,
            'user_prompt': 'test'
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def failing_tool():
            raise Exception("Tool failed")

        tools = {"fail": failing_tool}

        execute_single_tool(
            tool_name="fail",
            tool_args={},
            tool_id="call_fail",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify context was still cleared (finally block)
        mock_inject.assert_called_once()
        mock_clear.assert_called_once()

    @patch('connectonion.tool_executor.inject_xray_context')
    @patch('connectonion.tool_executor.clear_xray_context')
    def test_xray_context_not_cleared_if_not_found(self, mock_clear, mock_inject):
        """Test that xray context injection doesn't happen for non-existent tools."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)
        tools = {}

        execute_single_tool(
            tool_name="missing",
            tool_args={},
            tool_id="call_miss",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Tool not found - should return early without xray injection
        mock_inject.assert_not_called()
        mock_clear.assert_not_called()


class TestEventInvocation:
    """Test that events are properly invoked during tool execution."""

    def test_before_tool_event_invoked(self):
        """Test that before_tool event is invoked before execution."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def simple_tool():
            # Verify before_tool was already called
            assert mock_agent._invoke_events.call_count >= 1
            return "result"

        tools = {"tool": simple_tool}

        execute_single_tool(
            tool_name="tool",
            tool_args={},
            tool_id="call_before",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify before_each_tool was invoked
        mock_agent._invoke_events.assert_any_call('before_each_tool')

    def test_after_tool_event_invoked_on_success(self):
        """Test that after_tool event is invoked after successful execution."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def success_tool():
            return "success"

        tools = {"success": success_tool}

        tool_calls = [ToolCall(id="call_after", name="success", arguments={})]

        execute_and_record_tools(
            tool_calls=tool_calls,
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify after_each_tool was invoked
        mock_agent._invoke_events.assert_any_call('after_each_tool')

    def test_on_error_event_invoked_on_failure(self):
        """Test that on_error event is invoked when tool fails."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def failing_tool():
            raise RuntimeError("Failure")

        tools = {"fail": failing_tool}

        tool_calls = [ToolCall(id="call_onerr", name="fail", arguments={})]

        execute_and_record_tools(
            tool_calls=tool_calls,
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify on_error was invoked and after_each_tool also fires for all executions
        mock_agent._invoke_events.assert_any_call('on_error')
        mock_agent._invoke_events.assert_any_call('after_each_tool')


class TestMessageFormatting:
    """Test message formatting helpers with error scenarios."""

    def test_add_assistant_message_with_tool_calls(self):
        """Test that assistant message is correctly formatted."""
        messages = []
        tool_calls = [
            ToolCall(name="tool1", arguments={"x": 1}, id="call_1"),
            ToolCall(name="tool2", arguments={"y": 2}, id="call_2")
        ]

        _add_assistant_message(messages, tool_calls)

        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "assistant"
        assert msg.get("content") is None  # content key may be omitted when tool_calls present
        assert len(msg["tool_calls"]) == 2
        assert msg["tool_calls"][0]["id"] == "call_1"
        assert msg["tool_calls"][0]["function"]["name"] == "tool1"

    def test_add_tool_result_message(self):
        """Test that tool result message is correctly formatted."""
        messages = []
        _add_tool_result_message(messages, "call_123", "Tool result here")

        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "tool"
        assert msg["content"] == "Tool result here"
        assert msg["tool_call_id"] == "call_123"

    def test_add_tool_result_with_error_message(self):
        """Test that error messages are properly added as tool results."""
        messages = []
        error_result = "Error executing tool: ValueError('bad input')"
        _add_tool_result_message(messages, "call_err", error_result)

        msg = messages[0]
        assert msg["role"] == "tool"
        assert "Error executing tool" in msg["content"]
        assert msg["tool_call_id"] == "call_err"


class TestTraceEntryStructure:
    """Test trace entry structure for different scenarios."""

    def test_success_trace_entry_structure(self):
        """Test trace entry has all required fields on success."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 3
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def test_tool(x, y):
            return f"{x} + {y} = {x+y}"

        tools = {"test": test_tool}

        trace_entry = execute_single_tool(
            tool_name="test",
            tool_args={"x": 5, "y": 10},
            tool_id="call_success",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify all required fields
        assert trace_entry["type"] == "tool_execution"
        assert trace_entry["tool_name"] == "test"
        assert trace_entry["arguments"] == {"x": 5, "y": 10}
        assert trace_entry["call_id"] == "call_success"
        assert trace_entry["status"] == "success"
        assert trace_entry["result"] == "5 + 10 = 15"
        assert trace_entry["iteration"] == 3
        assert "timing" in trace_entry
        assert "timestamp" in trace_entry
        # Success should not have error fields
        assert "error" not in trace_entry
        assert "error_type" not in trace_entry

    def test_error_trace_entry_structure(self):
        """Test trace entry has error fields when tool fails."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }
        mock_agent._invoke_events = Mock()

        logger = Logger("test", log=False)

        def error_tool():
            raise ValueError("Invalid value")

        tools = {"error": error_tool}

        trace_entry = execute_single_tool(
            tool_name="error",
            tool_args={},
            tool_id="call_error",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify error-specific fields
        assert trace_entry["status"] == "error"
        assert trace_entry["error"] == "Invalid value"
        assert trace_entry["error_type"] == "ValueError"
        assert "Error executing tool" in trace_entry["result"]

    def test_not_found_trace_entry_structure(self):
        """Test trace entry structure when tool not found."""
        mock_agent = Mock()
        mock_agent.current_session = {
            'messages': [],
            'trace': [],
            'iteration': 1
        }

        logger = Logger("test", log=False)
        tools = {}

        trace_entry = execute_single_tool(
            tool_name="missing",
            tool_args={"param": "value"},
            tool_id="call_notfound",
            tools=tools,
            agent=mock_agent,
            logger=logger
        )

        # Verify not_found specific fields
        assert trace_entry["status"] == "not_found"
        assert "error" in trace_entry
        assert "not found" in trace_entry["error"]
        assert "not found" in trace_entry["result"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
