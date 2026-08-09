"""The co ai Claude Code handoff keeps provider policy out of model input."""

import importlib
import inspect
import json
from types import SimpleNamespace

import pytest

from connectonion.cli.co_ai.tools.claude_code import claude_code
from connectonion.useful_plugins.tool_approval import check_approval

claude_wrapper = importlib.import_module(
    "connectonion.cli.co_ai.tools.claude_code"
)
claude_library = importlib.import_module("connectonion.useful_tools.claude_code")


@pytest.mark.parametrize(
    ("mode", "permission_mode"),
    [
        ("safe", "default"),
        ("accept_edits", "acceptEdits"),
        ("ulw", "auto"),
    ],
)
def test_co_ai_mode_owns_claude_permission_mode(
    monkeypatch, tmp_path, mode, permission_mode
):
    seen = {}

    def fake_claude_code(**kwargs):
        seen.update(kwargs)
        return '{"provider":"claude_code","session_id":"s"}'

    monkeypatch.setattr(claude_wrapper, "run_claude_code", fake_claude_code)
    agent = SimpleNamespace(current_session={"mode": mode})

    result = claude_code(
        "fix it",
        session_id="s",
        cwd=str(tmp_path),
        model="sonnet",
        timeout=42,
        agent=agent,
    )

    assert result == '{"provider":"claude_code","session_id":"s"}'
    assert seen == {
        "prompt": "fix it",
        "session_id": "s",
        "cwd": str(tmp_path.resolve()),
        "permission_mode": permission_mode,
        "model": "sonnet",
        "timeout": 42,
        "agent": agent,
    }


def test_unknown_or_missing_mode_uses_provider_default(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        claude_wrapper,
        "run_claude_code",
        lambda **kwargs: calls.append(kwargs) or "result",
    )

    assert claude_code("one", cwd=str(tmp_path), agent=None) == "result"
    assert (
        claude_code(
            "two",
            cwd=str(tmp_path),
            agent=SimpleNamespace(current_session={"mode": "future"}),
        )
        == "result"
    )
    assert all(call["permission_mode"] == "default" for call in calls)


def test_model_cannot_select_claude_permission_mode():
    parameters = inspect.signature(claude_code).parameters
    assert "permission_mode" not in parameters
    assert parameters["agent"].default is None


@pytest.mark.parametrize("cwd", ["~definitely_no_such_user_776/repo", "\0"])
def test_invalid_cwd_stays_a_structured_library_error(cwd):
    result = json.loads(claude_code("inspect", cwd=cwd))

    assert result["provider"] == "claude_code"
    assert result["status"] == "error"
    assert "Working directory" in result["error"]


def test_resume_reapplies_mode_through_the_library_adapter(monkeypatch, tmp_path):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(
            stdout=json.dumps(
                {
                    "result": "continued",
                    "session_id": "session-old",
                    "is_error": False,
                }
            ),
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(claude_library, "_base_command", lambda: ["claude"])
    monkeypatch.setattr(claude_library, "_run_process", fake_run)
    result = json.loads(
        claude_code(
            "continue",
            cwd=str(tmp_path),
            session_id="session-old",
            agent=SimpleNamespace(current_session={"mode": "accept_edits"}),
        )
    )

    argv = calls[0][0]
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert argv[argv.index("--resume") + 1] == "session-old"
    assert calls[0][1]["cwd"] == str(tmp_path.resolve())
    assert result["resumed"] is True
    assert result["session_id"] == "session-old"


def test_structured_library_failure_passes_through(monkeypatch, tmp_path):
    monkeypatch.setattr(claude_library, "_base_command", lambda: None)

    result = json.loads(claude_code("inspect", cwd=str(tmp_path)))

    assert result["provider"] == "claude_code"
    assert result["status"] == "error"
    assert "CLI not found" in result["error"]


def test_outer_approval_does_not_duplicate_claude_permissions():
    io = SimpleNamespace(send=lambda *_: pytest.fail("outer approval must not prompt"))
    agent = SimpleNamespace(
        current_session={
            "mode": "safe",
            "pending_tool": {
                "id": "call-1",
                "name": "claude_code",
                "arguments": {"prompt": "fix it", "cwd": "/repo"},
            },
        },
        io=io,
        logger=None,
    )

    assert check_approval(agent) is None
