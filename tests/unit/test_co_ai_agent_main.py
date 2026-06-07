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
    assert agent.tools.get_instance("browserautomation")._headless is False
    assert agent.co_dir == Path(".co")


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
