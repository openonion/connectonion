"""Unit tests for ask_user tool."""
"""
LLM-Note: Tests for ask user

What it tests:
- Ask User functionality

Components under test:
- Module: ask_user
"""


import sys

import pytest
from unittest.mock import Mock
from connectonion.useful_tools.ask_user import ask_user

# The package re-exports the function under the module's own name, so
# `connectonion.useful_tools.ask_user` resolves to the function. Reach the module itself.
ask_user_module = sys.modules["connectonion.useful_tools.ask_user"]
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

    def _record_trace(self, entry, *, wire_extras=None):
        """Record trace entry (simplified for testing)."""
        import time
        if 'id' not in entry:
            entry['id'] = self._next_trace_id()
        if 'ts' not in entry:
            entry['ts'] = time.time()
        self.current_session['trace'].append(entry)
        if self.io:
            wire_entry = {**wire_extras, **entry} if wire_extras else entry
            self.io.send(wire_entry)

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

    def test_ask_user_with_fields(self):
        """ask_user includes fields in the event when provided."""
        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive.return_value = {"answer": '{"username":"me"}'}

        fields = [{"name": "username", "label": "Username", "type": "text"}]
        result = ask_user(agent, "Login?", options=[], fields=fields)

        agent.io.send.assert_called_once_with({
            "type": "ask_user",
            "question": "Login?",
            "options": [],
            "multi_select": False,
            "fields": fields,
        })
        assert result == '{"username":"me"}'

    def test_ask_user_empty_answer(self):
        """ask_user returns empty string if no answer in response."""
        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive.return_value = {}

        result = ask_user(agent, "Question?", options=["A", "B"])

        assert result == ""

    def test_interrupt_sets_stop_signal_instead_of_becoming_answer(self):
        from connectonion.core.interrupt import UserInterrupt

        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive.return_value = {"type": "INTERRUPT"}

        with pytest.raises(UserInterrupt):
            ask_user(agent, "Continue?", options=["Yes", "No"])

        assert agent.current_session["stop_signal"] == "Interrupted by user"

    def test_unanswered_question_is_not_treated_as_approval(self, monkeypatch):
        """With no io there is nobody to answer — one-shot runs and every
        deployed agent. This used to reply "decide from the request context",
        which reads as yes: an agent that correctly stopped to confirm an
        irreversible outward-facing action was told to go ahead anyway.

        Caught live — `co ai` drafted a company-wide Slack announcement, called
        ask_user for approval, got that string back, and posted it."""
        monkeypatch.delenv("OWNER_EMAIL", raising=False)
        agent = FakeAgent()
        assert agent.io is None

        result = ask_user(agent, "Post this to #general?", options=["Yes", "No"])

        lowered = result.lower()
        assert "not approval" in lowered
        assert "not answered" in lowered
        # Must not hand the decision back to the model.
        assert "decide from the request context" not in lowered
        # Names the actions it is gating, so the model knows what "this" covers.
        for action in ["send", "post", "delete", "overwrite", "deploy"]:
            assert action in lowered


class TestAskOwnerByEmail:
    """With no io, the owner's inbox is the only channel left to reach a human."""

    @pytest.fixture
    def owner(self, monkeypatch):
        monkeypatch.setenv("OWNER_EMAIL", "aaron@example.com")
        monkeypatch.setattr(ask_user_module.time, "sleep", lambda seconds: None)
        monkeypatch.setattr(
            ask_user_module.secrets, "token_hex", lambda _size: "request123"
        )
        return "aaron@example.com"

    def test_emails_the_owner_and_returns_their_reply(self, owner, monkeypatch):
        sent = {}
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: sent.update(to=to, subject=subject, message=message)
                            or {"success": True})
        inbox = [[{
            "id": "m1",
            "from": owner,
            "subject": "Re: [CO-ASK:request123] Your agent is asking",
            "message": "Yes, go ahead",
        }]]
        monkeypatch.setattr(ask_user_module, "get_emails", lambda last=10: inbox.pop(0) if inbox else [])
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        agent = FakeAgent()
        result = ask_user(agent, "Publish the event?", options=["Yes", "No"])

        assert result == "Yes, go ahead"
        assert sent["to"] == owner
        assert "Publish the event?" in sent["subject"]
        assert "[CO-ASK:request123]" in sent["subject"]
        assert "[CO-ASK:request123]" in sent["message"]
        assert "Yes" in sent["message"] and "No" in sent["message"]

    def test_unrelated_owner_email_is_not_mistaken_for_the_answer(self, owner, monkeypatch):
        """Sender identity without this request's tag is not authorization."""
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: {"success": True})
        unrelated = {
            "id": "other",
            "from": owner,
            "subject": "Lunch tomorrow",
            "message": "Yes, sounds good",
        }
        answer = {
            "id": "answer",
            "from": owner,
            "subject": "Re: [CO-ASK:request123] Your agent is asking",
            "message": "No, hold off",
        }
        inbox = [[unrelated], [unrelated, answer]]
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda last=10: inbox.pop(0) if inbox else [unrelated],
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(FakeAgent(), "Publish the event?", options=["Yes", "No"])

        assert result == "No, hold off"

    def test_quoted_question_is_stripped_from_the_reply(self, owner, monkeypatch):
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: {"success": True})
        reply = "482913\n\nOn Mon, Aug 11, 2026 at 9:02 AM agent wrote:\n> Your agent is asking: code?"
        inbox = [[{
            "id": "m1",
            "from": owner,
            "subject": "Re: [CO-ASK:request123] code",
            "message": reply,
        }]]
        monkeypatch.setattr(ask_user_module, "get_emails", lambda last=10: inbox.pop(0) if inbox else [])
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(FakeAgent(), "What is the SMS code?", options=[])

        assert result == "482913"

    def test_timeout_reports_unanswered_rather_than_approving(self, owner, monkeypatch):
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: {"success": True})
        monkeypatch.setattr(ask_user_module, "get_emails", lambda last=10: [])
        monkeypatch.setattr(ask_user_module, "REPLY_TIMEOUT", 0)

        result = ask_user(FakeAgent(), "Publish the event?", options=["Yes", "No"])

        assert "NOT ANSWERED" in result
        assert "not approval" in result.lower()

    def test_failed_send_reports_unanswered_rather_than_approving(self, owner, monkeypatch):
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: {"success": False, "error": "no credits"})
        monkeypatch.setattr(ask_user_module, "get_emails", lambda last=10: [])

        result = ask_user(FakeAgent(), "Publish the event?", options=["Yes", "No"])

        assert "NOT ANSWERED" in result
        assert "no credits" in result

    def test_transient_inbox_failure_does_not_become_an_answer(self, owner, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda to, subject, message: {"success": True},
        )
        answer = {
            "id": "m1",
            "from": owner.upper(),
            "subject": "RE: [CO-ASK:REQUEST123] answer",
            "message": "Wait",
        }
        inbox = [RuntimeError("temporary outage"), [answer]]

        def get_emails(last=10):
            value = inbox.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        monkeypatch.setattr(ask_user_module, "get_emails", get_emails)
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        assert ask_user(FakeAgent(), "Publish?", options=[]) == "Wait"

    def test_empty_correlated_reply_is_not_approval(self, owner, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda to, subject, message: {"success": True},
        )
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda last=10: [{
                "id": "m1",
                "from": owner,
                "subject": "Re: [CO-ASK:request123] answer",
                "message": "> quoted question only",
            }],
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(FakeAgent(), "Publish?", options=[])

        assert "NOT ANSWERED" in result
        assert "no answer" in result.lower()


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

    def test_interrupt_consumed_inside_ask_user_records_interrupted_trace(self):
        tools = ToolRegistry()
        tools.add(create_tool_from_function(ask_user))
        agent = FakeAgent()
        agent.io = Mock()
        agent.io.receive_all.return_value = []
        agent.io.receive.return_value = {"type": "INTERRUPT"}

        trace = execute_single_tool(
            tool_name="ask_user",
            tool_args={"question": "Continue?", "options": ["Yes", "No"]},
            tool_id="call_interrupt",
            tools=tools,
            agent=agent,
            logger=Logger("test", log=False),
        )

        assert trace["status"] == "interrupted"
        assert trace["result"] == "Interrupted by user"
        assert agent.current_session["stop_signal"] == "Interrupted by user"

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
