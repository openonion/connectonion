"""Tests for CLI ai and trust command handlers.

LLM-Note: Tests for cli commands ai trust

What it tests:
- Cli Commands Ai Trust functionality

Components under test:
- Module: cli_commands_ai_trust
"""

import os

import pytest
import typer

import connectonion.cli.commands.ai_commands as ai_mod
import connectonion.cli.commands.trust_commands as trust_mod
from connectonion.cli.co_ai.agent import GLOBAL_CO_DIR
from connectonion.core.exceptions import LLMAuthenticationError
from connectonion.useful_plugins import eval as eval_plugin


def test_handle_ai_calls_start_server(monkeypatch):
    called = {}
    created = {}

    def fake_create_agent(**kwargs):
        agent = object()
        created.update(kwargs)
        created["agent"] = agent
        return agent

    def fake_start_server(agent, **kwargs):
        called.update(kwargs)
        called["agent"] = agent

    monkeypatch.setattr("connectonion.cli.co_ai.agent.create_agent", fake_create_agent)
    monkeypatch.setattr("connectonion.cli.co_ai.main.start_server", fake_start_server)

    ai_mod.handle_ai(
        port=1111,
        model="m",
        max_iterations=3,
        yolo=True,
        yolo_turns=7,
    )

    assert called["port"] == 1111
    assert called["model"] == "m"
    assert called["max_iterations"] == 3
    assert called["yolo"] is True
    assert called["yolo_turns"] == 7
    assert callable(called["agent_factory"])
    assert called["agent"] is created["agent"]
    assert created["model"] == "m"
    assert created["max_iterations"] == 3
    assert created["co_dir"] == GLOBAL_CO_DIR
    assert created["yolo_turns"] == 7
    assert created["extra_plugins"] == ()


def test_handle_ai_enables_eval_only_when_requested(monkeypatch, capsys):
    created = {}

    class FakeAgent:
        def input(self, prompt):
            return "done"

    def fake_create_agent(**kwargs):
        created.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(
        "connectonion.cli.co_ai.agent.create_agent",
        fake_create_agent,
    )

    ai_mod.handle_ai(prompt="task", evaluate=True)

    assert created["extra_plugins"] == (eval_plugin,)
    assert capsys.readouterr().out.endswith("done\n")


def test_handle_ai_one_shot_keeps_plain_mode_unchanged(monkeypatch, capsys):
    created = {}

    class FakeAgent:
        def input(self, prompt):
            created["prompt"] = prompt
            return "done"

    def fake_create_agent(**kwargs):
        created.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(
        "connectonion.cli.co_ai.agent.create_agent",
        fake_create_agent,
    )

    ai_mod.handle_ai(prompt="task", yolo=False, yolo_turns=9)

    assert created["prompt"] == "task"
    assert created["yolo_turns"] is None
    assert capsys.readouterr().out.endswith("done\n")


def test_handle_ai_prepares_private_acp_state_dir(tmp_path, monkeypatch):
    selected = tmp_path / "isolated" / "acp-state"
    called = {}

    async def fake_serve_acp(**kwargs):
        called.update(kwargs)

    monkeypatch.setattr(
        "connectonion.cli.co_ai.acp_server.serve_acp",
        fake_serve_acp,
    )

    ai_mod.handle_ai(acp=True, state_dir=selected)

    assert called["state_dir"] == selected.resolve()
    assert selected.is_dir()
    if os.name != "nt":
        assert selected.stat().st_mode & 0o777 == 0o700


def test_isolated_agent_keeps_global_config_and_redirects_only_state(
    tmp_path,
    monkeypatch,
):
    created = {}

    def fake_create_agent(**kwargs):
        created.update(kwargs)
        return object()

    monkeypatch.setattr(
        "connectonion.cli.co_ai.agent.create_agent",
        fake_create_agent,
    )

    state_dir = tmp_path / "state"
    ai_mod._create_agent(
        "test",
        2,
        False,
        2,
        resumable=True,
        state_dir=state_dir,
    )

    assert created["co_dir"] == GLOBAL_CO_DIR
    assert created["state_dir"] == state_dir


@pytest.mark.skipif(os.name == "nt", reason="Windows symlink creation needs privileges")
def test_handle_ai_rejects_a_symlink_state_dir(tmp_path, monkeypatch, capsys):
    target = tmp_path / "target"
    target.mkdir()
    selected = tmp_path / "state"
    selected.symlink_to(target, target_is_directory=True)
    served = False

    async def fake_serve_acp(**_kwargs):
        nonlocal served
        served = True

    monkeypatch.setattr(
        "connectonion.cli.co_ai.acp_server.serve_acp",
        fake_serve_acp,
    )

    with pytest.raises(typer.Exit) as caught:
        ai_mod.handle_ai(acp=True, state_dir=selected)

    assert caught.value.exit_code == 2
    assert served is False
    assert "state directory is unavailable" in capsys.readouterr().out


def test_handle_ai_reports_a_provider_failure_without_a_traceback(monkeypatch, capsys):
    class FakeAgent:
        def input(self, prompt):
            raise LLMAuthenticationError(
                RuntimeError("raw upstream implementation detail"),
                model="co/claude-sonnet-4",
            )

    monkeypatch.setattr(
        "connectonion.cli.co_ai.agent.create_agent", lambda **kwargs: FakeAgent()
    )

    with pytest.raises(typer.Exit) as caught:
        ai_mod.handle_ai(prompt="task")

    output = capsys.readouterr().out
    assert caught.value.exit_code == 1
    assert "Model request failed" in output
    assert "service-side configuration" in output
    assert "raw upstream implementation detail" not in output


def test_handle_ai_does_not_hide_programmer_errors(monkeypatch):
    class FakeAgent:
        def input(self, prompt):
            raise TypeError("our bug")

    monkeypatch.setattr(
        "connectonion.cli.co_ai.agent.create_agent", lambda **kwargs: FakeAgent()
    )

    with pytest.raises(TypeError, match="our bug"):
        ai_mod.handle_ai(prompt="task")


def test_trust_commands_list_and_actions(tmp_path, monkeypatch):
    # Point CO_DIR at temp path and create lists
    co = tmp_path / ".co"
    co.mkdir()
    monkeypatch.chdir(tmp_path)
    (co / "contacts.txt").write_text("c1\n", encoding="utf-8")
    (co / "whitelist.txt").write_text("w1\n", encoding="utf-8")
    (co / "blocklist.txt").write_text("b1\n", encoding="utf-8")

    monkeypatch.setattr(trust_mod, "load_admins", lambda: ["a1"])
    monkeypatch.setattr(trust_mod, "get_self_address", lambda: "a1")

    # Smoke test list
    trust_mod.handle_trust_list()

    monkeypatch.setattr(trust_mod, "get_level", lambda addr: "contact")
    trust_mod.handle_trust_level("addr")

    monkeypatch.setattr(trust_mod, "promote_to_contact", lambda addr: "ok")
    monkeypatch.setattr(trust_mod, "promote_to_whitelist", lambda addr: "ok")
    monkeypatch.setattr(trust_mod, "demote_to_stranger", lambda addr: "ok")
    monkeypatch.setattr(trust_mod, "block", lambda addr, reason="": "ok")
    monkeypatch.setattr(trust_mod, "unblock", lambda addr: "ok")
    monkeypatch.setattr(trust_mod, "add_admin", lambda addr: "ok")
    monkeypatch.setattr(trust_mod, "remove_admin", lambda addr: "ok")

    trust_mod.handle_trust_add("addr")
    trust_mod.handle_trust_add("addr", whitelist=True)
    trust_mod.handle_trust_remove("addr")
    trust_mod.handle_trust_block("addr", reason="r")
    trust_mod.handle_trust_unblock("addr")
    trust_mod.handle_admin_add("addr")
    trust_mod.handle_admin_remove("addr")
