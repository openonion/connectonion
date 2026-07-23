"""Unit tests for connectonion/useful_tools/codex.py (native codex app-server).

The CodexAppServer client is replaced with a fake that drives the on_event /
on_approval callbacks, so these run without spawning `codex app-server`. A
real-binary end-to-end lives in tests/e2e/real_api/test_real_codex.py.
"""

import importlib
import json
from unittest.mock import patch

from connectonion.useful_tools.codex import codex

# `from .codex import codex` makes useful_tools.codex the function, shadowing the
# module; reach the module (for CodexAppServer / helpers) via importlib.
codex_module = importlib.import_module("connectonion.useful_tools.codex")


class FakeServer:
    """Stand-in CodexAppServer that simulates one turn via callbacks."""
    last = None

    def __init__(self, command, cwd=None, on_event=None, on_approval=None):
        self.command = command
        self.cwd = cwd
        self.on_event = on_event
        self.on_approval = on_approval
        self.calls = []
        self.approval_decision = None
        FakeServer.last = self

    def start(self):
        self.calls.append("start")

    def close(self):
        self.calls.append("close")

    def initialize(self, timeout=60):
        self.calls.append("initialize")

    def start_thread(self, sandbox="workspace-write", model="", timeout=60):
        self.calls.append(("start_thread", sandbox, model))
        return "thread-1"

    def resume_thread(self, thread_id, timeout=60):
        self.calls.append(("resume_thread", thread_id))
        return thread_id

    def run_turn(self, thread_id, prompt, cwd="", timeout=600):
        self.calls.append(("run_turn", thread_id, prompt))
        self.on_event({"kind": "agent_message", "text": "Hello "})
        self.on_event({"kind": "tool_start", "id": "c1", "name": "pytest"})
        self.approval_decision = self.on_approval({"command": ["pytest", "-q"]})
        self.on_event({"kind": "tool_end", "id": "c1", "name": "pytest", "failed": False})
        self.on_event({"kind": "agent_message", "text": "world"})
        return {"status": "completed", "usage": {"input_tokens": 5}}


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
    with patch.object(codex_module, "CodexAppServer", FakeServer), \
         patch.object(codex_module, "_base_command", return_value=["codex", "app-server"]):
        return json.loads(codex(**kwargs))


class TestCodexRun:
    def test_new_thread_accumulates_message(self):
        agent = _Agent(_IO(approve=True))
        result = _run(prompt="fix", cwd=".", approval="auto", agent=agent)

        assert result["provider"] == "codex"
        assert result["session_id"] == "thread-1"
        assert result["resumed"] is False
        assert result["last_message"] == "Hello world"
        assert result["exit_code"] == 0
        assert result["usage"]["input_tokens"] == 5

    def test_resume_uses_resume_thread(self):
        agent = _Agent(_IO())
        result = _run(prompt="continue", session_id="prev", approval="auto", agent=agent)

        assert result["resumed"] is True
        assert result["session_id"] == "prev"
        assert ("resume_thread", "prev") in FakeServer.last.calls

    def test_sandbox_and_model_passed_to_thread_start(self):
        _run(prompt="fix", sandbox="read-only", model="gpt-5-codex", approval="auto", agent=_Agent(_IO()))
        assert ("start_thread", "read-only", "gpt-5-codex") in FakeServer.last.calls

    def test_missing_binary_errors(self):
        with patch.object(codex_module, "_base_command", return_value=None):
            result = json.loads(codex("fix"))
        assert "codex CLI not found" in result["error"]

    def test_invalid_sandbox(self):
        assert "Invalid sandbox" in json.loads(codex("fix", sandbox="yolo"))["error"]

    def test_invalid_approval(self):
        assert "Invalid approval" in json.loads(codex("fix", approval="whenever"))["error"]


class TestFrontendEventVocabulary:
    """Codex steps must be forwarded as the SDK's native tool_call/tool_result
    events (not a custom type), so the frontend renders them unchanged."""

    def test_tool_call_and_result_emitted(self):
        agent = _Agent(_IO())
        _run(prompt="fix", approval="auto", agent=agent)

        types = [et for et, _ in agent.io.events]
        assert "tool_call" in types and "tool_result" in types

        call = next(d for et, d in agent.io.events if et == "tool_call")
        assert call["tool_id"] == "c1" and call["name"] == "pytest"
        result = next(d for et, d in agent.io.events if et == "tool_result")
        assert result["tool_id"] == "c1" and result["status"] == "done"

    def test_failed_tool_maps_to_error(self):
        agent = _Agent(_IO())

        class FailServer(FakeServer):
            def run_turn(self, thread_id, prompt, cwd="", timeout=600):
                self.on_event({"kind": "tool_start", "id": "x", "name": "rm"})
                self.on_event({"kind": "tool_end", "id": "x", "name": "rm", "failed": True})
                return {"status": "completed"}

        with patch.object(codex_module, "CodexAppServer", FailServer), \
             patch.object(codex_module, "_base_command", return_value=["codex", "app-server"]):
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
        assert FakeServer.last.approval_decision == "approved"
        assert agent.io.asked == []

    def test_manual_approved_renders_card_and_allows(self):
        agent = _Agent(_IO(approve=True))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeServer.last.approval_decision == "approved"
        assert agent.io.asked and agent.io.asked[0][0] == "codex"
        # the approval summary shows the actual command
        assert "pytest" in agent.io.asked[0][1]["action"]

    def test_manual_rejected_denies(self):
        agent = _Agent(_IO(approve=False))
        _run(prompt="fix", approval="manual", agent=agent)
        assert FakeServer.last.approval_decision == "denied"

    def test_manual_without_io_denies(self):
        assert codex_module._decide_approval({"command": ["x"]}, "manual", agent=None) == "denied"


class TestApprovalSummary:
    def test_command_joined(self):
        assert codex_module._approval_summary({"command": ["git", "push"]}) == "git push"

    def test_falls_back_to_reason(self):
        assert codex_module._approval_summary({"reason": "edit file"}) == "edit file"
