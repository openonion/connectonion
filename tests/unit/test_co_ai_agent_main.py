"""Tests for co_ai agent creation and server entrypoint.

LLM-Note: Tests for co ai agent main

What it tests:
- Co Ai Agent Main functionality

Components under test:
- Module: co_ai_agent_main
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import connectonion.cli.co_ai.agent as agent_mod
import connectonion.cli.co_ai.main as main_mod
from connectonion import ClaudeCodePlugin, CodexPlugin
from connectonion.cli.co_ai.plugins.native_coding_agent_routing import (
    reject_raw_codex_launch,
    route_explicit_codex_request,
)
from connectonion.useful_plugins import eval as eval_plugin
from connectonion.useful_plugins.tool_approval.approval import load_permission_patterns


@pytest.fixture(autouse=True)
def avoid_real_global_owner_setup(monkeypatch):
    """Server tests exercise hosting without writing to the developer's home."""
    monkeypatch.setattr(main_mod, "_prepare_owner_onboarding", lambda _co_dir: False)


def test_managed_delegation_permissions_are_explicit(tmp_path):
    """Nested coding agents own inner approval without reopening unknown tools."""
    agent = SimpleNamespace(current_session={'permissions': {}})

    agent_mod.grant_managed_delegation_permissions(agent)

    assert set(agent.current_session['permissions']) == {
        'codex', 'claude_code'
    }
    assert all(
        permission['allowed'] is True
        and permission['source'] == 'safe'
        for permission in agent.current_session['permissions'].values()
    )
    shared_exec_permissions = load_permission_patterns(tmp_path / '.co')
    assert not {'codex', 'claude_code'} & set(
        shared_exec_permissions
    )


def test_create_coding_agent(monkeypatch, tmp_path):
    class FakeLLM:
        model = "fake-model"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", lambda *a, **k: "BASE")
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "CTX")
    monkeypatch.setattr(agent_mod, "GLOBAL_CO_DIR", tmp_path / ".co")

    agent = agent_mod.create_coding_agent(model="fake", max_iterations=5)

    assert agent.name == "oo"
    assert agent.max_iterations == 5
    assert "BASE" in agent.system_prompt
    assert "CTX" in agent.system_prompt
    # FileTools is registered as a tool class
    assert "file_tools" in agent.tools._tools or any("file" in t.lower() for t in agent.tools._tools)
    assert "ask_user" in agent.tools._tools
    assert "codex" in agent.tools._tools
    codex_plugins = [
        plugin for plugin in agent.installed_plugins
        if isinstance(plugin, CodexPlugin)
    ]
    assert len(codex_plugins) == 1
    assert agent.tools.get("codex")._bound_instance is codex_plugins[0]
    codex_schema = agent.tools.get("codex").to_function_schema()["parameters"]
    assert set(codex_schema["properties"]) == {
        "prompt",
        "session_id",
        "cwd",
        "model",
        "timeout",
        "summary",
    }
    assert codex_schema.get("required", []) == ["summary"]
    assert "claude_code" in agent.tools._tools
    claude_plugins = [
        plugin for plugin in agent.installed_plugins
        if isinstance(plugin, ClaudeCodePlugin)
    ]
    assert len(claude_plugins) == 1
    assert agent.tools.get("claude_code")._bound_instance is claude_plugins[0]
    claude_schema = agent.tools.get("claude_code").to_function_schema()["parameters"]
    assert set(claude_schema["properties"]) == {
        "prompt",
        "session_id",
        "cwd",
        "model",
        "timeout",
        "summary",
    }
    assert claude_schema["required"] == ["prompt", "cwd", "summary"]
    assert "acp_agent" not in agent.tools._tools
    # agent.py removes this stdin-blocking helper; it must not come back
    assert "wait_for_manual_login" not in agent.tools._tools
    # The browser is driven through the `co browser` CLI, so no in-process
    # BrowserAutomation is wired in — bash carries every browser action, and
    # 40 tool schemas stay out of the request.
    assert agent.tools.get_instance("browserautomation") is None
    assert "bash" in agent.tools._tools
    assert route_explicit_codex_request in agent.events["after_user_input"]
    assert reject_raw_codex_launch in agent.events["before_each_tool"]
    assert agent.events["before_each_tool"].index(reject_raw_codex_launch) < agent.events[
        "before_each_tool"
    ].index(agent_mod.tool_approval[-1])
    assert "todolist" in agent.tools._instances
    assert "enter_plan_mode" not in agent.tools._tools
    assert "exit_plan_and_implement" not in agent.tools._tools
    assert "write_plan" not in agent.tools._tools
    assert agent.co_dir == Path(".co")
    # bind_browser_session existed only because hosted co ai ran every panel's
    # turns on one in-process BrowserAutomation. The `co browser` daemon owns
    # tabs itself (`-t <tab>`), so the workaround is gone.
    from connectonion.useful_plugins.bind_browser_session import _bind_browser_session
    assert _bind_browser_session not in agent.events["before_each_tool"]
    for handler in eval_plugin:
        assert handler not in agent.events[handler._event_type]

    evaluated = agent_mod.create_coding_agent(
        model="fake",
        max_iterations=5,
        extra_plugins=(eval_plugin,),
    )
    for handler in eval_plugin:
        assert handler in evaluated.events[handler._event_type]


def test_co_ai_codex_uses_the_plugin_invocation_lifecycle(monkeypatch, tmp_path):
    class FakeLLM:
        model = "fake-model"

    import connectonion.plugins.coding_agents as coding_agents

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", lambda *a, **k: "BASE")
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "")
    monkeypatch.setattr(
        coding_agents,
        "_run_codex",
        lambda **kwargs: '{"provider":"codex","session_id":"s1","exit_code":0}',
    )
    monkeypatch.chdir(tmp_path)
    agent = agent_mod.create_agent(model="fake", max_iterations=1)
    agent.current_session = {
        "trace": [],
        "mode": "read-only",
        "_active_tool_call_id": "call-1",
    }

    agent.tools.codex("inspect", agent=agent)

    lifecycle = [
        entry for entry in agent.current_session["trace"]
        if entry["type"] == "provider_invocation"
    ]
    assert [entry["status"] for entry in lifecycle] == ["running", "completed"]
    assert all(entry["parentToolCallId"] == "call-1" for entry in lifecycle)


def test_co_ai_claude_uses_the_plugin_invocation_lifecycle(monkeypatch, tmp_path):
    class FakeLLM:
        model = "fake-model"

    import connectonion.plugins.coding_agents as coding_agents

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", lambda *a, **k: "BASE")
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "")
    monkeypatch.setattr(
        coding_agents,
        "_run_claude_code",
        lambda **kwargs: json.dumps({
            "provider": "claude_code",
            "session_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "exit_code": 0,
        }),
    )
    monkeypatch.chdir(tmp_path)
    agent = agent_mod.create_agent(model="fake", max_iterations=1)
    agent.current_session = {
        "trace": [],
        "mode": "read-only",
        "_active_tool_call_id": "call-2",
    }

    agent.tools.claude_code("inspect", cwd=".", agent=agent)

    lifecycle = [
        entry for entry in agent.current_session["trace"]
        if entry["type"] == "provider_invocation"
    ]
    assert [entry["status"] for entry in lifecycle] == ["running", "completed"]
    assert all(entry["parentToolCallId"] == "call-2" for entry in lifecycle)


def test_start_server_hosts_provided_agent(monkeypatch):
    agent = SimpleNamespace(name="agent")
    called = {}

    def fake_host(agent, port, trust, co_dir=None, relay_url=None, **kwargs):
        called.update({
            "agent": agent,
            "port": port,
            "trust": trust,
            "relay_url": relay_url,
            **kwargs,
        })

    monkeypatch.setattr(main_mod, "host", fake_host)
    main_mod.start_server(agent, port=1234)

    assert called["port"] == 1234
    assert called["trust"] == "careful"
    assert called["relay_url"] is None
    assert called["agent"] is agent
    assert "acp_agent_factory" not in called


def test_start_server_offers_full_access_without_activating_it(monkeypatch):
    agent = SimpleNamespace(name="agent")
    hosted = {}

    def fake_host(value, **kwargs):
        hosted["agent"] = value
        hosted.update(kwargs)

    monkeypatch.setattr(main_mod, "host", fake_host)

    main_mod.start_server(
        agent,
        full_access=True,
        full_access_turns=7,
    )

    assert hosted["agent"] is agent
    assert agent._full_access_turns == 7
    assert agent._full_access_needs_activation is False


def test_start_server_prepares_owner_invite_without_printing_it(monkeypatch):
    agent = SimpleNamespace(name="agent")
    printed = []
    prepared = []
    secret = "NEVER-PRINT-THIS2"

    def prepare(co_dir):
        prepared.append(co_dir)
        return True

    monkeypatch.setattr(main_mod, "_prepare_owner_onboarding", prepare)
    monkeypatch.setattr(main_mod, "host", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "connectonion.cli.commands.project_cmd_lib.console.print",
        lambda message: printed.append(message),
    )
    monkeypatch.setenv("CO_INVITE_CODE", secret)

    main_mod.start_server(agent)

    assert prepared == [Path.home() / ".co"]
    output = " ".join(printed)
    assert "co keys --reveal" in output
    assert secret not in output


def test_role_reaches_the_assembler(monkeypatch, tmp_path):
    """The factory→assembler hop was untested: assemble_prompt(role=) had tests
    and the template's role string had tests, but nothing checked that
    create_agent actually passes one to the other. A dropped kwarg would leave
    every agent domain-neutral with no test turning red."""
    class FakeLLM:
        model = "fake-model"

    seen = {}

    def fake_assemble(*args, **kwargs):
        seen["role"] = kwargs.get("role", "<not passed>")
        return "BASE"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", fake_assemble)
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "")
    monkeypatch.setattr(agent_mod, "GLOBAL_CO_DIR", tmp_path / ".co")

    agent_mod.create_agent(model="fake", max_iterations=1)
    assert seen["role"] == "coding", "`co ai` must stay a coding agent by default"

    agent_mod.create_agent(model="fake", max_iterations=1, role=None)
    assert seen["role"] is None, "a deployed agent must be able to drop the domain"

    agent_mod.create_agent(model="fake", max_iterations=1, role="support")
    assert seen["role"] == "support"


def test_the_real_prompt_differs_with_and_without_a_role(tmp_path, monkeypatch):
    """End of the chain, unmocked: a role must actually change what the agent
    is told, and the no-role prompt must not call it a coding agent."""
    class FakeLLM:
        model = "fake-model"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "")
    monkeypatch.setattr(agent_mod, "GLOBAL_CO_DIR", tmp_path / ".co")

    coding = agent_mod.create_agent(model="fake", max_iterations=1).system_prompt
    plain = agent_mod.create_agent(model="fake", max_iterations=1, role=None).system_prompt

    assert len(coding) > len(plain)
    assert "# Tool: Codex delegation" in coding
    assert "# Tool: Claude Code delegation" in coding
    assert "Native coding-agent routing is mandatory" in coding
    assert "call `codex()` without `prompt`" in coding
    assert "you are a coding agent" not in plain.lower()
    # Behaviour that every agent needs survives dropping the role.
    for prompt in (coding, plain):
        assert "Executing Actions with Care" in prompt
