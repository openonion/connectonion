"""Unit tests for connectonion/useful_tools/codex.py (ACP transport only).

The ACPClient is replaced with a fake that drives the on_event / on_permission
callbacks, so these run without spawning codex-acp. Real-binary end-to-end lives
in tests/e2e/real_api/test_real_codex.py.
"""

import importlib
import json
from unittest.mock import patch

from connectonion.useful_tools.codex import codex

# `from .codex import codex` makes useful_tools.codex the function, shadowing the
# module; reach the module (for ACPClient / helpers) via importlib.
codex_module = importlib.import_module("connectonion.useful_tools.codex")

ALLOW_REJECT = [
    {"optionId": "allow-1", "name": "Allow", "kind": "allow_once"},
    {"optionId": "reject-1", "name": "Reject", "kind": "reject_once"},
]


class FakeACPClient:
    """Stand-in ACPClient that simulates one codex-acp turn via callbacks."""
    last = None

    def __init__(self, command, cwd=None, on_event=None, on_permission=None):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event
        self.on_permission = on_permission
        self.calls = []
        self.permission_result = None
        FakeACPClient.last = self

    def start(self):
        self.calls.append("start")

    def close(self):
        self.calls.append("close")

    def initialize(self, timeout=60):
        return {"protocolVersion": 1, "agentInfo": {"name": "codex-acp"}}

    def new_session(self, timeout=60):
        self.calls.append("new_session")
        return "acp-sid-1"

    def load_session(self, session_id, timeout=60):
        self.calls.append(("load_session", session_id))
        return session_id

    def prompt(self, session_id, text, timeout=600):
        self.calls.append(("prompt", session_id, text))
        self.on_event({"acp_update": "agent_message_chunk", "text": "Hello "})
        self.on_event({"acp_update": "agent_thought_chunk", "text": "(thinking hard)"})
        self.on_event({"acp_update": "tool_call", "tool_call_id": "c1",
                       "tool_kind": "execute", "title": "run pytest", "status": "pending"})
        self.permission_result = self.on_permission({"title": "run pytest"}, ALLOW_REJECT)
        self.on_event({"acp_update": "tool_call_update", "tool_call_id": "c1", "status": "completed"})
        self.on_event({"acp_update": "agent_message_chunk", "text": "world"})
        return "end_turn"


class _IO:
    def __init__(self, approve=True):
        self.approve = approve
        self.events = []
        self.asked = []

    def log(self, event_type, **data):
        self.events.append((event_type, data))

    def request_approval(self, tool, arguments):
        self.asked.append((tool, arguments))
        return self.approve


class _Agent:
    def __init__(self, io):
        self.io = io


def _run(**kwargs):
    with patch.object(codex_module, "ACPClient", FakeACPClient), \
         patch.object(codex_module, "_base_command", return_value=["fake-codex-acp"]):
        return json.loads(codex(**kwargs))


class TestCodexRun:
    def test_new_session_accumulates_message(self):
        agent = _Agent(_IO(approve=True))
        result = _run(prompt="fix", cwd=".", approval="auto", agent=agent)

        assert result["provider"] == "codex"
        assert result["session_id"] == "acp-sid-1"
        assert result["resumed"] is False
        assert result["last_message"] == "Hello world"    # thought excluded
        assert result["exit_code"] == 0

    def test_resume_uses_load_session(self):
        agent = _Agent(_IO())
        result = _run(prompt="continue", session_id="prev-sid", approval="auto", agent=agent)

        assert result["resumed"] is True
        assert result["session_id"] == "prev-sid"
        assert ("load_session", "prev-sid") in FakeACPClient.last.calls

    def test_sandbox_and_model_become_config_overrides(self):
        _run(prompt="fix", sandbox="read-only", model="gpt-5-codex", approval="auto", agent=_Agent(_IO()))
        cmd = FakeACPClient.last.command
        assert 'sandbox_mode="read-only"' in cmd
        assert 'model="gpt-5-codex"' in cmd

    def test_missing_binary_errors(self):
        with patch.object(codex_module, "_base_command", return_value=None):
            result = json.loads(codex("fix"))
        assert "codex-acp not found" in result["error"]

    def test_invalid_sandbox(self):
        result = json.loads(codex("fix", sandbox="yolo"))
        assert "Invalid sandbox" in result["error"]

    def test_invalid_approval(self):
        result = json.loads(codex("fix", approval="whenever"))
        assert "Invalid approval" in result["error"]


class TestFrontendEventVocabulary:
    """Codex steps must be forwarded as the SDK's native tool_call/tool_result
    events (not a custom type), so the frontend renders them unchanged."""

    def test_tool_call_and_result_emitted(self):
        agent = _Agent(_IO())
        _run(prompt="fix", approval="auto", agent=agent)

        types = [et for et, _ in agent.io.events]
        assert "tool_call" in types
        assert "tool_result" in types

        call = next(d for et, d in agent.io.events if et == "tool_call")
        assert call["tool_id"] == "c1"
        assert call["name"] == "run pytest"

        result = next(d for et, d in agent.io.events if et == "tool_result")
        assert result["tool_id"] == "c1"        # same id → SDK correlates them
        assert result["status"] == "done"

    def test_failed_tool_maps_to_error(self):
        agent = _Agent(_IO())

        class FailClient(FakeACPClient):
            def prompt(self, session_id, text, timeout=600):
                self.on_event({"acp_update": "tool_call", "tool_call_id": "x",
                               "title": "rm", "status": "pending"})
                self.on_event({"acp_update": "tool_call_update", "tool_call_id": "x", "status": "failed"})
                return "end_turn"

        with patch.object(codex_module, "ACPClient", FailClient), \
             patch.object(codex_module, "_base_command", return_value=["x"]):
            codex("fix", approval="auto", agent=agent)

        result = next(d for et, d in agent.io.events if et == "tool_result")
        assert result["status"] == "error"

    def test_no_custom_codex_event_type(self):
        agent = _Agent(_IO())
        _run(prompt="fix", approval="auto", agent=agent)
        assert all(et != "codex_event" for et, _ in agent.io.events)


class TestApproval:
    def test_auto_approves_without_asking(self):
        agent = _Agent(_IO(approve=False))     # io says no, but auto ignores io
        _run(prompt="fix", approval="auto", agent=agent)
        assert FakeACPClient.last.permission_result == "allow-1"
        assert agent.io.asked == []

    def test_manual_approved_renders_card_and_allows(self):
        agent = _Agent(_IO(approve=True))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeACPClient.last.permission_result == "allow-1"
        assert agent.io.asked and agent.io.asked[0][0] == "codex"

    def test_manual_rejected_denies(self):
        agent = _Agent(_IO(approve=False))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeACPClient.last.permission_result == "reject-1"

    def test_manual_without_io_denies(self):
        result = codex_module._decide_permission({"title": "x"}, ALLOW_REJECT, "manual", agent=None)
        assert result == "reject-1"


class TestOptionPick:
    def test_matches_kind(self):
        assert codex_module._option_id(ALLOW_REJECT, "allow") == "allow-1"
        assert codex_module._option_id(ALLOW_REJECT, "reject") == "reject-1"

    def test_falls_back_to_first(self):
        opts = [{"optionId": "only", "kind": "something"}]
        assert codex_module._option_id(opts, "allow") == "only"
