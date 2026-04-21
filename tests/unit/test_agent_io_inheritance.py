"""
Unit tests for Agent IO inheritance via ContextVar.

When host() sets agent.io, child agents created inside tools should
automatically inherit the parent's IO via ContextVar propagation.
"""

import pytest
from unittest.mock import Mock
from connectonion.core.agent import Agent, _parent_io
from tests.utils.mock_helpers import MockLLM, LLMResponseBuilder


class TestIOInheritance:

    def test_io_defaults_to_none(self):
        """Agent.io defaults to None when no parent IO is set."""
        agent = Agent(name="test", llm=MockLLM(), log=False)
        assert agent.io is None

    def test_io_inherits_from_context_var(self):
        """Agent.io picks up parent IO from ContextVar."""
        mock_io = Mock()
        token = _parent_io.set(mock_io)
        try:
            agent = Agent(name="child", llm=MockLLM(), log=False)
            assert agent.io is mock_io
        finally:
            _parent_io.reset(token)

    def test_io_propagated_during_input(self):
        """When agent.io is set, calling input() propagates IO to ContextVar."""
        mock_io = Mock()
        captured_io = []

        def capture_tool() -> str:
            """Capture current IO context. Returns: status"""
            captured_io.append(_parent_io.get())
            return "done"

        agent = Agent(
            name="parent",
            llm=MockLLM(responses=[
                LLMResponseBuilder.tool_call_response("capture_tool", {}),
                LLMResponseBuilder.text_response("done"),
            ]),
            tools=[capture_tool],
            log=False,
        )
        agent.io = mock_io

        agent.input("test")

        assert len(captured_io) == 1
        assert captured_io[0] is mock_io

    def test_io_context_cleaned_up_after_input(self):
        """ContextVar is reset after input() returns."""
        mock_io = Mock()
        agent = Agent(
            name="parent",
            llm=MockLLM(responses=[LLMResponseBuilder.text_response("hi")]),
            log=False,
        )
        agent.io = mock_io

        agent.input("test")

        # ContextVar should be reset to default (None)
        assert _parent_io.get() is None

    def test_no_io_no_propagation(self):
        """When agent.io is None, ContextVar is not touched."""
        agent = Agent(
            name="test",
            llm=MockLLM(responses=[LLMResponseBuilder.text_response("hi")]),
            log=False,
        )
        assert agent.io is None

        agent.input("test")

        assert _parent_io.get() is None
