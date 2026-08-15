"""Tests for co_ai agent creation and server entrypoint."""
"""
LLM-Note: Tests for co ai agent main

What it tests:
- Co Ai Agent Main functionality

Components under test:
- Module: co_ai_agent_main
"""


from types import SimpleNamespace
from pathlib import Path

import connectonion.cli.co_ai.agent as agent_mod
import connectonion.cli.co_ai.main as main_mod
from connectonion.useful_plugins import eval as eval_plugin


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
    # agent.py removes this stdin-blocking helper; it must not come back
    assert "wait_for_manual_login" not in agent.tools._tools
    # The browser is driven through the `co browser` CLI, so no in-process
    # BrowserAutomation is wired in — bash carries every browser action, and
    # 40 tool schemas stay out of the request.
    assert agent.tools.get_instance("browserautomation") is None
    assert "bash" in agent.tools._tools
    assert agent.co_dir == Path(".co")
    # bind_browser_session existed only because hosted co ai ran every panel's
    # turns on one in-process BrowserAutomation. The `co browser` daemon owns
    # tabs itself (`-t <tab>`), so the workaround is gone.
    from connectonion.useful_plugins.bind_browser_session import _bind_browser_session
    assert _bind_browser_session not in agent.events["before_each_tool"]
    registered = [handler for handlers in agent.events.values() for handler in handlers]
    assert all(handler not in registered for handler in eval_plugin)
    # Recent session records remain available for debugging; only the two
    # scoring-model calls are opt-in, and logger retention bounds disk usage.
    assert agent.logger.enable_sessions is True


def test_co_ai_eval_is_explicitly_opt_in(monkeypatch, tmp_path):
    class FakeLLM:
        model = "fake-model"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", lambda *a, **k: "BASE")
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "")

    agent = agent_mod.create_agent(
        model="fake",
        max_iterations=1,
        co_dir=tmp_path / ".co",
        extra_plugins=(eval_plugin,),
    )

    registered = [handler for handlers in agent.events.values() for handler in handlers]
    assert all(handler in registered for handler in eval_plugin)
    assert agent.logger.enable_sessions is True


def test_start_server_hosts_provided_agent(monkeypatch):
    agent = SimpleNamespace(name="agent")
    called = {}

    def fake_host(agent, port, trust, co_dir=None, relay_url=None):
        called.update({"agent": agent, "port": port, "trust": trust, "relay_url": relay_url})

    monkeypatch.setattr(main_mod, "host", fake_host)

    main_mod.start_server(agent, port=1234)

    assert called["port"] == 1234
    assert called["trust"] == "careful"
    assert called["relay_url"] is None
    assert called["agent"] is agent


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
    assert "you are a coding agent" not in plain.lower()
    # Behaviour that every agent needs survives dropping the role.
    for prompt in (coding, plain):
        assert "Executing Actions with Care" in prompt
