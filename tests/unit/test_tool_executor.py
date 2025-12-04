"""Unit tests for connectonion/tool_executor.py"""

import pytest
from unittest.mock import Mock
from connectonion.tool_executor import execute_single_tool, _add_assistant_message
from connectonion.tool_registry import ToolRegistry
from connectonion.tool_factory import create_tool_from_function
from connectonion.logger import Logger
from connectonion.llm import ToolCall


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
