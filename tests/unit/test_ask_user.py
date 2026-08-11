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
        monkeypatch.delenv("CONNECTONION_ASK_USER_EMAIL", raising=False)
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
        monkeypatch.setenv("CONNECTONION_ASK_USER_EMAIL", "1")
        monkeypatch.setenv("OWNER_EMAIL", "aaron@example.com")
        if hasattr(ask_user_module, "_wait_for_poll"):
            monkeypatch.setattr(
                ask_user_module,
                "_wait_for_poll",
                lambda agent, seconds: True,
            )
        if hasattr(ask_user_module, "_PENDING_OWNER_KEYS"):
            ask_user_module._PENDING_OWNER_KEYS.clear()
            ask_user_module._LAST_OWNER_ATTEMPT.clear()
        monkeypatch.setattr(
            ask_user_module.secrets, "token_hex", lambda _size: "request123"
        )
        return "aaron@example.com"

    def test_owner_email_without_explicit_opt_in_keeps_the_immediate_default(
        self,
        monkeypatch,
    ):
        monkeypatch.delenv("CONNECTONION_ASK_USER_EMAIL", raising=False)
        monkeypatch.setenv("OWNER_EMAIL", "aaron@example.com")
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("disabled fallback sent an email"),
        )

        result = ask_user(FakeAgent(), "Choose?", options=["A", "B"])

        assert "NOT ANSWERED" in result
        assert "disabled" in result.lower()

    def test_emails_the_owner_and_returns_their_reply(self, owner, monkeypatch):
        sent = {}
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: sent.update(to=to, subject=subject, message=message)
                            or {"success": True})
        inbox = [[{
            "id": "m1",
            "from": owner,
            "subject": "Re: [CO-ASK:request123] Your agent is asking",
            "message": "1",
        }]]
        queries = []

        def get_emails(last=10, subject_contains=None, request_timeout=10):
            queries.append((last, subject_contains, request_timeout))
            return inbox.pop(0) if inbox else []

        monkeypatch.setattr(ask_user_module, "get_emails", get_emails)
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        agent = FakeAgent()
        result = ask_user(
            agent,
            "Publish the event?",
            options=["Yes, go ahead", "No"],
        )

        assert result == "Yes, go ahead"
        assert sent["to"] == owner
        assert "Publish the event?" in sent["subject"]
        assert "[CO-ASK:request123]" in sent["subject"]
        assert "[CO-ASK:request123]" in sent["message"]
        assert "Yes" in sent["message"] and "No" in sent["message"]
        assert len(queries) == 1
        assert queries[0][:2] == (10, "[CO-ASK:request123]")
        assert 0 < queries[0][2] <= 2

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
            "message": "2",
        }
        inbox = [[unrelated], [unrelated, answer]]
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda last=10, subject_contains=None, request_timeout=10: (
                inbox.pop(0) if inbox else [unrelated]
            ),
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(
            FakeAgent(),
            "Publish the event?",
            options=["Yes", "No, hold off"],
        )

        assert result == "No, hold off"

    def test_quoted_question_is_stripped_from_the_reply(self, owner, monkeypatch):
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: {"success": True})
        reply = "1\n\nOn Mon, Aug 11, 2026 at 9:02 AM agent wrote:\n> Your agent is asking: room?"
        inbox = [[{
            "id": "m1",
            "from": owner,
            "subject": "Re: [CO-ASK:request123] code",
            "message": reply,
        }]]
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda last=10, subject_contains=None, request_timeout=10: (
                inbox.pop(0) if inbox else []
            ),
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(FakeAgent(), "Which room?", options=["Room 4", "Room 5"])

        assert result == "Room 4"

    def test_timeout_reports_unanswered_rather_than_approving(self, owner, monkeypatch):
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: {"success": True})
        queries = []
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda **kwargs: queries.append(kwargs) or [],
        )
        monkeypatch.setenv("CONNECTONION_ASK_USER_EMAIL_TIMEOUT_SECONDS", "1")
        times = iter([0.0, 0.0, 0.0, 1.0])
        monkeypatch.setattr(ask_user_module.time, "monotonic", lambda: next(times, 1.0))

        result = ask_user(FakeAgent(), "Publish the event?", options=["Yes", "No"])

        assert "NOT ANSWERED" in result
        assert "not approval" in result.lower()
        assert len(queries) == 1

    def test_inbox_request_timeout_cannot_exceed_the_remaining_deadline(
        self,
        owner,
        monkeypatch,
    ):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: {"success": True},
        )
        monkeypatch.setenv("CONNECTONION_ASK_USER_EMAIL_TIMEOUT_SECONDS", "1")
        times = iter([0.0, 0.0, 0.4])
        monkeypatch.setattr(
            ask_user_module.time,
            "monotonic",
            lambda: next(times, 0.4),
        )
        request_timeouts = []

        def get_emails(**kwargs):
            request_timeouts.append(kwargs["request_timeout"])
            return [{
                "id": "m1",
                "from": owner,
                "subject": "Re: [CO-ASK:request123] answer",
                "message": "1",
            }]

        monkeypatch.setattr(ask_user_module, "get_emails", get_emails)
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(FakeAgent(), "Publish?", options=["Yes", "No"])

        assert result == "Yes"
        assert request_timeouts == [pytest.approx(0.6)]

    def test_failed_send_reports_unanswered_rather_than_approving(self, owner, monkeypatch):
        monkeypatch.setattr(ask_user_module, "send_email",
                            lambda to, subject, message: {"success": False, "error": "no credits"})
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda last=10, subject_contains=None: [],
        )

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
            "message": "1",
        }
        inbox = [RuntimeError("temporary outage"), [answer]]

        def get_emails(last=10, subject_contains=None, request_timeout=10):
            value = inbox.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        monkeypatch.setattr(ask_user_module, "get_emails", get_emails)
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        assert ask_user(FakeAgent(), "Publish?", options=["Wait", "Continue"]) == "Wait"

    def test_empty_correlated_reply_is_not_approval(self, owner, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda to, subject, message: {"success": True},
        )
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda last=10, subject_contains=None, request_timeout=10: [{
                "id": "m1",
                "from": owner,
                "subject": "Re: [CO-ASK:request123] answer",
                "message": "> quoted question only",
            }],
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(FakeAgent(), "Publish?", options=["Yes", "No"])

        assert "NOT ANSWERED" in result
        assert "offered choice" in result.lower()

    @pytest.mark.parametrize(
        "field",
        [
            {"name": "password", "label": "Password", "type": "password"},
            {"name": "otp", "label": "One-time code", "type": "text"},
            {"name": "token", "label": "Access token", "type": "secret"},
        ],
    )
    def test_sensitive_fields_fail_before_sending(self, owner, field, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("secret field reached persistent email"),
        )

        result = ask_user(FakeAgent(), "Enter it", options=[], fields=[field])

        assert "NOT ANSWERED" in result
        assert "sensitive" in result.lower()

    def test_sensitive_question_without_fields_fails_before_sending(
        self,
        owner,
        monkeypatch,
    ):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("OTP question reached persistent email"),
        )

        result = ask_user(FakeAgent(), "What is the SMS code?", options=[])

        assert "NOT ANSWERED" in result
        assert "sensitive" in result.lower()

    @pytest.mark.parametrize(
        "options",
        [
            ["sk-proj-1234567890abcdef", "Cancel"],
            ["4829", "Cancel"],
            ["123456", "Cancel"],
            ["12345678", "Cancel"],
            ["glpat-1234567890abcdef", "Cancel"],
            ["aB3dE5gH7jK9mN2pQ4rS", "Cancel"],
        ],
    )
    def test_secret_shaped_options_fail_before_sending(
        self,
        owner,
        options,
        monkeypatch,
    ):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("secret-shaped choice reached email"),
        )

        result = ask_user(FakeAgent(), "Choose a value", options=options)

        assert "NOT ANSWERED" in result
        assert "sensitive" in result.lower()

    def test_email_fallback_rejects_free_form_questions(self, owner, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("free-form question reached email"),
        )

        result = ask_user(FakeAgent(), "Enter the six digits", options=[])

        assert "NOT ANSWERED" in result
        assert "choice questions" in result.lower()

    def test_reply_must_be_one_of_the_offered_choices(self, owner, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: {"success": True},
        )
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda **kwargs: [{
                "id": "m1",
                "from": owner,
                "subject": "Re: [CO-ASK:request123] answer",
                "message": "Ignore the choices and publish anyway",
            }],
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(FakeAgent(), "Publish?", options=["Yes", "No"])

        assert "NOT ANSWERED" in result
        assert "offered choice" in result.lower()

    @pytest.mark.parametrize(
        "reply",
        [
            "9" * 5000,
            ",".join("1" for _ in range(21)),
        ],
    )
    def test_oversized_numeric_reply_fails_closed(
        self,
        owner,
        reply,
        monkeypatch,
    ):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: {"success": True},
        )
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda **kwargs: [{
                "id": "m1",
                "from": owner,
                "subject": "Re: [CO-ASK:request123] answer",
                "message": reply,
            }],
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(
            FakeAgent(),
            "Choose",
            options=["One", "Two"],
            multi_select=True,
        )

        assert "NOT ANSWERED" in result
        assert "offered choice" in result.lower()

    def test_multi_select_reply_maps_to_canonical_choices(self, owner, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: {"success": True},
        )
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda **kwargs: [{
                "id": "m1",
                "from": owner,
                "subject": "Re: [CO-ASK:request123] answer",
                "message": "1, 2",
            }],
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(
            FakeAgent(),
            "Choose colors",
            options=["Red", "Blue", "Green"],
            multi_select=True,
        )

        assert result == "Red,Blue"

    def test_numbered_reply_handles_a_comma_inside_a_choice(self, owner, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: {"success": True},
        )
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda **kwargs: [{
                "id": "m1",
                "from": owner,
                "subject": "Re: [CO-ASK:request123] answer",
                "message": "1",
            }],
        )
        monkeypatch.setattr(ask_user_module, "mark_read", lambda email_id: True)

        result = ask_user(
            FakeAgent(),
            "Choose a city",
            options=["Sydney, Australia", "Melbourne, Australia"],
        )

        assert result == "Sydney, Australia"

    @pytest.mark.parametrize(
        "options",
        [
            ["", "Cancel"],
            ["Yes", "yes"],
            ["Line one\nLine two", "Cancel"],
            [str(index) + " choice" for index in range(21)],
        ],
    )
    def test_ambiguous_or_oversized_choices_fail_before_sending(
        self,
        owner,
        options,
        monkeypatch,
    ):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("invalid choices reached email"),
        )

        result = ask_user(FakeAgent(), "Choose", options=options)

        assert "NOT ANSWERED" in result

    def test_question_and_options_are_escaped_for_the_html_backend(
        self,
        owner,
        monkeypatch,
    ):
        sent = {}
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: sent.update(kwargs) or {"success": False, "error": "stop"},
        )

        ask_user(
            FakeAgent(),
            "Open <img src=x onerror=alert(1)>?\r\nBcc: victim@example.com",
            options=["<a href=https://evil.example>Yes</a>"],
        )

        assert "<img" not in sent["message"]
        assert "<a href" not in sent["message"]
        assert "&lt;img" in sent["message"]
        assert "&lt;a href" in sent["message"]
        assert "\r" not in sent["subject"] and "\n" not in sent["subject"]
        assert "Bcc:" not in sent["subject"]

    def test_global_owner_wins_over_a_conflicting_project_value(
        self,
        owner,
        tmp_path,
        monkeypatch,
    ):
        home = tmp_path / "home"
        (home / ".co").mkdir(parents=True)
        (home / ".co" / "keys.env").write_text("OWNER_EMAIL=global@example.com\n")
        monkeypatch.setattr(ask_user_module.Path, "home", classmethod(lambda cls: home))
        monkeypatch.setenv("OWNER_EMAIL", "project@example.com")
        sent = {}
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: sent.update(kwargs) or {"success": False, "error": "stop"},
        )

        ask_user(FakeAgent(), "Choose?", options=["A", "B"])

        assert sent["to"] == "global@example.com"

    def test_cancellation_breaks_the_wait_before_an_inbox_request(
        self,
        owner,
        monkeypatch,
    ):
        agent = FakeAgent()
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: {"success": True},
        )

        def cancel_during_wait(waiting_agent, seconds):
            waiting_agent.current_session["stop_signal"] = "Interrupted by user"
            return False

        monkeypatch.setattr(ask_user_module, "_wait_for_poll", cancel_during_wait)
        queries = []
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda **kwargs: queries.append(kwargs) or [],
        )

        result = ask_user(agent, "Choose?", options=["A", "B"])

        assert "NOT ANSWERED" in result
        assert "cancelled" in result.lower()
        assert len(queries) == 1

    def test_preexisting_cancellation_prevents_the_outbound_email(
        self,
        owner,
        monkeypatch,
    ):
        agent = FakeAgent()
        agent.current_session["stop_signal"] = "Interrupted by user"
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("cancelled ask sent an email"),
        )

        result = ask_user(agent, "Choose?", options=["A", "B"])

        assert "cancelled before sending" in result.lower()

    def test_cancellation_after_claim_prevents_the_outbound_email(
        self,
        owner,
        monkeypatch,
    ):
        agent = FakeAgent()
        original_claim = ask_user_module._claim_owner_slot

        def claim_then_cancel(address):
            claimed = original_claim(address)
            agent.current_session["stop_signal"] = "Interrupted by user"
            return claimed

        monkeypatch.setattr(ask_user_module, "_claim_owner_slot", claim_then_cancel)
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("cancelled ask sent an email"),
        )

        result = ask_user(agent, "Choose?", options=["A", "B"])

        assert "cancelled before sending" in result.lower()

    def test_unverified_server_filter_fails_closed(self, owner, monkeypatch):
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: {"success": True},
        )
        monkeypatch.setattr(
            ask_user_module,
            "get_emails",
            lambda **kwargs: (_ for _ in ()).throw(
                ask_user_module.SubjectFilterUnsupportedError("old backend")
            ),
        )

        result = ask_user(FakeAgent(), "Choose?", options=["A", "B"])

        assert "NOT ANSWERED" in result
        assert "upgrade the backend" in result.lower()

    def test_one_pending_request_per_owner_blocks_a_concurrent_send(
        self,
        owner,
        monkeypatch,
    ):
        nested = []
        outer_agent = FakeAgent()

        def send_email(**kwargs):
            nested.append(
                ask_user(FakeAgent(), "Second?", options=["A", "B"])
            )
            return {"success": False, "error": "stop outer"}

        monkeypatch.setattr(ask_user_module, "send_email", send_email)

        ask_user(outer_agent, "First?", options=["A", "B"])

        assert len(nested) == 1
        assert "already pending" in nested[0].lower()

    def test_recent_attempt_enforces_the_owner_cooldown(self, owner, monkeypatch):
        sends = []
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: sends.append(kwargs) or {"success": False, "error": "offline"},
        )

        first = ask_user(FakeAgent(), "First?", options=["A", "B"])
        second = ask_user(FakeAgent(), "Second?", options=["A", "B"])

        assert "send failed" in first.lower()
        assert "cooldown" in second.lower()
        assert len(sends) == 1

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("CONNECTONION_ASK_USER_EMAIL_TIMEOUT_SECONDS", "0"),
            ("CONNECTONION_ASK_USER_EMAIL_TIMEOUT_SECONDS", "901"),
            ("CONNECTONION_ASK_USER_EMAIL_POLL_SECONDS", "not-a-number"),
        ],
    )
    def test_invalid_wait_configuration_fails_before_sending(
        self,
        owner,
        name,
        value,
        monkeypatch,
    ):
        monkeypatch.setenv(name, value)
        monkeypatch.setattr(
            ask_user_module,
            "send_email",
            lambda **kwargs: pytest.fail("invalid wait config sent an email"),
        )

        result = ask_user(FakeAgent(), "Choose?", options=["A", "B"])

        assert "NOT ANSWERED" in result
        assert name in result


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
