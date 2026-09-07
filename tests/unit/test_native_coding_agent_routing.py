"""COAI routes explicit Codex work through the native adapter."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from connectonion.cli.co_ai.plugins.native_coding_agent_routing import (
    is_explicit_codex_request,
    reject_raw_codex_launch,
    route_explicit_codex_request,
)


@pytest.mark.parametrize(
    "prompt",
    [
        "run Codex",
        "open the Codex session",
        "ask Codex to fix the parser",
        "please use codex for this task",
        "/codex inspect the failing test",
        "打开 Codex",
        "用 codex 修复测试",
    ],
)
def test_explicit_codex_requests_are_recognized(prompt):
    assert is_explicit_codex_request(prompt)


@pytest.mark.parametrize(
    "prompt",
    [
        "How does Codex work?",
        "update the Codex documentation",
        "the variable is named codex_path",
        "do not use Codex",
        "never open Codex for this task",
        "compare Codex with Claude Code",
    ],
)
def test_mentions_and_negative_requests_do_not_force_delegation(prompt):
    assert not is_explicit_codex_request(prompt)


def test_explicit_intent_adds_one_hidden_native_route_reminder():
    agent = SimpleNamespace(
        current_session={
            "user_prompt": "open Codex",
            "messages": [{"role": "user", "content": "open Codex"}],
        }
    )

    route_explicit_codex_request(agent)

    assert agent.current_session["provider_route"] == "codex"
    reminder = agent.current_session["messages"][-1]
    assert reminder["internal"] is True
    assert "call `codex()` now" in reminder["content"].lower()
    assert "omit `prompt`" in reminder["content"]


@pytest.mark.parametrize(
    "tool_name,arguments",
    [
        ("bash", {"command": "codex exec 'fix the tests'"}),
        ("shell", {"command": "/usr/local/bin/codex --sandbox read-only"}),
        ("run", {"command": "cd repo && env FOO=1 codex exec fix"}),
        ("run_in_dir", {"command": "sudo -u builder codex exec fix"}),
        ("run_background", {"command": "nohup codex exec fix"}),
        ("bash", {"command": "bash -lc 'codex exec fix'"}),
        ("bash", {"command": "echo $(codex exec fix)"}),
        ("bash", {"command": "npx @openai/codex exec fix"}),
        ("bash", {"command": "npm exec -- codex exec fix"}),
    ],
)
def test_raw_codex_launches_are_rejected_with_native_next_action(
    tool_name, arguments
):
    io = SimpleNamespace(send=MagicMock())
    agent = SimpleNamespace(
        current_session={
            "pending_tool": {"name": tool_name, "arguments": arguments}
        },
        io=io,
    )

    with pytest.raises(ValueError, match=r"Call codex\(\)"):
        reject_raw_codex_launch(agent)

    frame = io.send.call_args.args[0]
    assert frame["type"] == "tool_blocked"
    assert frame["reason"] == "native_provider_required"
    assert frame["provider"] == "codex"


@pytest.mark.parametrize(
    "command",
    [
        "which codex",
        "command -v codex",
        "echo codex",
        "rg -n codex docs/",
        "grep codex README.md",
        "python -c 'print(\"codex\")'",
        "bash -lc 'echo codex'",
        "git commit -m 'document codex adapter'",
    ],
)
def test_unrelated_codex_mentions_are_not_blocked(command):
    agent = SimpleNamespace(
        current_session={
            "pending_tool": {"name": "bash", "arguments": {"command": command}}
        },
        io=None,
    )

    reject_raw_codex_launch(agent)
