"""The co ai Codex handoff keeps one explicit permission boundary."""

import importlib
import inspect
from types import SimpleNamespace

import pytest

from connectonion.cli.co_ai.tools.codex import codex
from connectonion.useful_plugins.tool_approval import check_approval

codex_module = importlib.import_module("connectonion.cli.co_ai.tools.codex")
library_module = importlib.import_module("connectonion.useful_tools.codex")


@pytest.mark.parametrize(
    ("mode", "sandbox", "approval"),
    [
        ("safe", "read-only", "manual"),
        ("accept_edits", "workspace-write", "manual"),
        ("ulw", "workspace-write", "deny"),
    ],
)
def test_co_ai_mode_owns_the_codex_policy(monkeypatch, mode, sandbox, approval):
    seen = {}

    def fake_codex(**kwargs):
        seen.update(kwargs)
        return '{"provider":"codex","session_id":"s"}'

    monkeypatch.setattr(codex_module, "run_codex", fake_codex)
    agent = SimpleNamespace(current_session={"mode": mode})

    result = codex(
        "fix it",
        session_id="s",
        cwd="/repo",
        model="gpt-5",
        timeout=42,
        agent=agent,
    )

    assert result == '{"provider":"codex","session_id":"s"}'
    assert seen == {
        "prompt": "fix it",
        "session_id": "s",
        "cwd": "/repo",
        "sandbox": sandbox,
        "model": "gpt-5",
        "timeout": 42,
        "approval": approval,
        "agent": agent,
    }


def test_unknown_or_missing_mode_fails_closed_to_manual_read_only(monkeypatch):
    calls = []
    monkeypatch.setattr(
        codex_module,
        "run_codex",
        lambda **kwargs: calls.append(kwargs) or "result",
    )

    assert codex("one", cwd="/repo", agent=None) == "result"
    assert (
        codex(
            "two",
            cwd="/repo",
            agent=SimpleNamespace(current_session={"mode": "future"}),
        )
        == "result"
    )
    assert all(call["sandbox"] == "read-only" for call in calls)
    assert all(call["approval"] == "manual" for call in calls)


@pytest.mark.parametrize("mode", ["safe", "accept_edits", "ulw"])
def test_hosted_contact_is_confined_to_read_only_without_prompts(monkeypatch, mode):
    seen = {}
    monkeypatch.setattr(
        codex_module,
        "run_codex",
        lambda **kwargs: seen.update(kwargs) or "result",
    )
    agent = SimpleNamespace(
        current_session={
            "mode": mode,
            "requester": {"address": "0xcontact", "level": "contact"},
        }
    )

    assert codex("inspect", cwd="/repo", agent=agent) == "result"
    assert seen["sandbox"] == "read-only"
    assert seen["approval"] == "deny"


def test_mode_policy_is_reapplied_through_the_resume_protocol(monkeypatch, tmp_path):
    calls = []

    class FakeServer:
        def __init__(
            self, command, cwd=None, on_event=None, on_approval=None, cancelled=None
        ):
            self.on_event = on_event

        def start(self):
            pass

        def initialize(self, timeout=60):
            pass

        def refresh_account(self, timeout=60):
            pass

        def start_thread(self, **kwargs):
            calls.append(("start", kwargs))
            return "thread-1"

        def resume_thread(self, thread_id, **kwargs):
            calls.append(("resume", {"thread_id": thread_id, **kwargs}))
            return thread_id

        def run_turn(self, thread_id, prompt, cwd="", timeout=600):
            self.on_event({"kind": "agent_message", "text": "done"})
            return {"status": "completed"}

        def close(self):
            pass

    monkeypatch.setattr(library_module, "CodexAppServer", FakeServer)
    monkeypatch.setattr(
        library_module, "_base_command", lambda: ["codex", "app-server"]
    )
    monkeypatch.setattr(codex_module, "run_codex", library_module.codex)

    safe = SimpleNamespace(current_session={"mode": "safe"})
    yolo = SimpleNamespace(current_session={"mode": "ulw"})
    first = codex("inspect", cwd=str(tmp_path), agent=safe)
    resumed = codex(
        "continue",
        cwd=str(tmp_path),
        session_id="thread-1",
        agent=yolo,
    )

    assert '"session_id": "thread-1"' in first
    assert '"resumed": true' in resumed
    assert calls[0][1]["sandbox"] == "read-only"
    assert calls[0][1]["approval_policy"] == "untrusted"
    assert calls[1][1]["sandbox"] == "workspace-write"
    assert calls[1][1]["approval_policy"] == "never"


def test_model_cannot_select_codex_approval_or_sandbox():
    parameters = inspect.signature(codex).parameters
    assert "approval" not in parameters
    assert "sandbox" not in parameters
    assert parameters["agent"].default is None


def test_outer_approval_does_not_duplicate_codex_action_approval():
    io = SimpleNamespace(send=lambda *_: pytest.fail("outer approval must not prompt"))
    agent = SimpleNamespace(
        current_session={
            "mode": "safe",
            "permissions": {
                "codex": {
                    "allowed": True,
                    "source": "safe",
                    "reason": "managed delegation owns inner approval",
                }
            },
            "pending_tool": {
                "id": "call-1",
                "name": "codex",
                "arguments": {"prompt": "fix it", "cwd": "/repo"},
            },
        },
        io=io,
        logger=None,
    )

    assert check_approval(agent) is None
