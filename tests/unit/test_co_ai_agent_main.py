"""Tests for co_ai agent creation and server entrypoint.

LLM-Note: Tests for co ai agent main

What it tests:
- Co Ai Agent Main functionality

Components under test:
- Module: co_ai_agent_main
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import connectonion.cli.co_ai.agent as agent_mod
import connectonion.cli.co_ai.main as main_mod
from connectonion.cli.co_ai.one_shot_sessions import (
    SessionSnapshotError,
    load_snapshot,
    save_snapshot,
)
from connectonion.network.host.acp_gateway import ACPPrincipal
from connectonion.useful_plugins.tool_approval.approval import load_permission_patterns


def test_managed_delegation_permissions_are_explicit(tmp_path):
    """Nested coding agents own inner approval without reopening unknown tools."""
    agent = SimpleNamespace(current_session={'permissions': {}})

    agent_mod.grant_managed_delegation_permissions(agent)

    assert set(agent.current_session['permissions']) == {'codex', 'claude_code'}
    assert all(
        permission['allowed'] is True
        and permission['source'] == 'safe'
        for permission in agent.current_session['permissions'].values()
    )
    shared_exec_permissions = load_permission_patterns(tmp_path / '.co')
    assert not {'codex', 'claude_code'} & set(shared_exec_permissions)


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
    codex_schema = agent.tools.get("codex").to_function_schema()["parameters"]
    assert set(codex_schema["properties"]) == {
        "prompt",
        "session_id",
        "cwd",
        "model",
        "timeout",
    }
    assert codex_schema["required"] == ["prompt", "cwd"]
    assert "claude_code" in agent.tools._tools
    claude_schema = agent.tools.get("claude_code").to_function_schema()["parameters"]
    assert set(claude_schema["properties"]) == {
        "prompt",
        "session_id",
        "cwd",
        "model",
        "timeout",
    }
    assert claude_schema["required"] == ["prompt", "cwd"]
    # agent.py removes this stdin-blocking helper; it must not come back
    assert "wait_for_manual_login" not in agent.tools._tools
    # The browser is driven through the `co browser` CLI, so no in-process
    # BrowserAutomation is wired in — bash carries every browser action, and
    # 40 tool schemas stay out of the request.
    assert agent.tools.get_instance("browserautomation") is None
    assert "bash" in agent.tools._tools
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
    assert callable(called["acp_agent_factory"])


def test_network_acp_sessions_are_principal_scoped_and_full_access_is_admin_only(
    monkeypatch,
    tmp_path,
):
    agent = SimpleNamespace(name="agent")
    called = {}
    monkeypatch.setattr(main_mod.Path, "home", lambda: tmp_path)
    global_co_dir = tmp_path / ".co"
    global_co_dir.mkdir()
    (global_co_dir / "host.yaml").write_text(
        "max_file_size: 2\n"
        "max_files_per_request: 4\n"
        "max_acp_upload_storage: 20\n"
        "max_acp_upload_files: 40\n",
        encoding="utf-8",
    )

    def fake_host(_agent, **kwargs):
        called.update(kwargs)

    monkeypatch.setattr(main_mod, "host", fake_host)
    main_mod.start_server(agent, yolo=True, yolo_turns=7)
    factory = called["acp_agent_factory"]

    def principal(address, level, *, method="browser_ticket"):
        return ACPPrincipal(
            address=address,
            level=level,
            recipient="0xrecipient",
            origin="https://chat.openonion.ai",
            auth_method=method,
            authenticated_at=1.0,
        )

    contact = factory(principal("0xcontact", "contact"))
    same_contact = factory(principal("0xcontact", "contact"))
    other_contact = factory(principal("0xother", "contact"))
    signed_contact = factory(
        principal("0xcontact", "contact", method="signed_headers")
    )
    admin = factory(principal("0xadmin", "admin"))

    assert contact._session_co_dir == same_contact._session_co_dir
    assert contact._session_co_dir != other_contact._session_co_dir
    assert contact._session_co_dir != signed_contact._session_co_dir
    assert contact._session_co_dir.is_relative_to(
        tmp_path / ".co" / "acp-principals"
    )
    assert contact._yolo is False
    assert contact._max_attachment_bytes == 2 * 1024 * 1024
    assert contact._max_attachments == 4
    assert contact._max_upload_storage_bytes == 20 * 1024 * 1024
    assert contact._max_upload_files == 40
    assert admin._yolo is True
    assert admin._yolo_turns == 7

    session_id = "40c0397c-972b-4133-899b-5ab4cc5c4883"
    snapshot = {
        "session_id": session_id,
        "messages": [],
        "trace": [],
        "turn": 0,
        "mode": ":read-only",
        "plan": [],
    }
    save_snapshot(contact._session_co_dir, snapshot, {}, cwd=tmp_path)
    loaded, _ = load_snapshot(
        same_contact._session_co_dir,
        session_id,
        cwd=tmp_path,
    )
    assert loaded["session_id"] == session_id
    with pytest.raises(SessionSnapshotError, match="was not found"):
        load_snapshot(other_contact._session_co_dir, session_id, cwd=tmp_path)


def test_network_acp_workspace_is_captured_when_server_starts(monkeypatch, tmp_path):
    launch_dir = tmp_path / "launch"
    later_dir = tmp_path / "later"
    launch_dir.mkdir()
    later_dir.mkdir()
    agent = SimpleNamespace(name="agent")
    called = {}
    monkeypatch.chdir(launch_dir)

    def fake_host(_agent, **kwargs):
        called.update(kwargs)

    monkeypatch.setattr(main_mod, "host", fake_host)
    main_mod.start_server(agent)
    monkeypatch.chdir(later_dir)

    principal = ACPPrincipal(
        address="0xcontact",
        level="contact",
        recipient="0xrecipient",
        origin="https://chat.openonion.ai",
        auth_method="browser_ticket",
        authenticated_at=1.0,
    )
    network_agent = called["acp_agent_factory"](principal)

    assert network_agent._network_workspace.path == launch_dir.resolve()
    assert network_agent._network_workspace.closed is True


def test_network_acp_workspace_closes_when_host_raises(monkeypatch, tmp_path):
    from connectonion.cli.co_ai import acp_server as acp_server_mod

    captured = []
    real_capture = acp_server_mod.capture_network_workspace

    def capture(path):
        workspace = real_capture(path)
        captured.append(workspace)
        return workspace

    def fail_host(*_args, **_kwargs):
        raise RuntimeError("host startup failed")

    # start_server imports the function lazily from acp_server.
    monkeypatch.setattr("connectonion.cli.co_ai.acp_server.capture_network_workspace", capture)
    monkeypatch.setattr(main_mod, "host", fail_host)

    with pytest.raises(RuntimeError, match="host startup failed"):
        main_mod.start_server(SimpleNamespace(name="agent"))

    assert captured and captured[0].closed is True


def test_network_acp_session_namespace_is_workspace_scoped(monkeypatch, tmp_path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    agent = SimpleNamespace(name="agent")
    factories = []
    monkeypatch.setattr(main_mod.Path, "home", lambda: tmp_path)

    def fake_host(_agent, **kwargs):
        factories.append(kwargs["acp_agent_factory"])

    monkeypatch.setattr(main_mod, "host", fake_host)
    principal = ACPPrincipal(
        address="0xcontact",
        level="contact",
        recipient="0xrecipient",
        origin="https://chat.openonion.ai",
        auth_method="browser_ticket",
        authenticated_at=1.0,
    )

    monkeypatch.chdir(first_dir)
    main_mod.start_server(agent)
    monkeypatch.chdir(second_dir)
    main_mod.start_server(agent)

    first_agent = factories[0](principal)
    second_agent = factories[1](principal)
    assert first_agent._session_co_dir != second_agent._session_co_dir


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
    assert "you are a coding agent" not in plain.lower()
    # Behaviour that every agent needs survives dropping the role.
    for prompt in (coding, plain):
        assert "Executing Actions with Care" in prompt
