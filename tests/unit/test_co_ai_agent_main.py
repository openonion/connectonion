"""Tests for co_ai agent creation and server entrypoint."""

from types import SimpleNamespace

import connectonion.cli.co_ai.agent as agent_mod
import connectonion.cli.co_ai.main as main_mod


def test_create_coding_agent(monkeypatch):
    class FakeLLM:
        model = "fake-model"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", lambda *a, **k: "BASE")
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "CTX")

    agent = agent_mod.create_coding_agent(model="fake", max_iterations=5, auto_approve=True)

    assert agent.name == "oo"
    assert agent.max_iterations == 5
    assert "BASE" in agent.system_prompt
    assert "CTX" in agent.system_prompt
    assert hasattr(agent, "writer")
    assert agent.writer.mode == "auto"


def test_start_server_calls_host(monkeypatch):
    created = []

    def fake_create(*args, **kwargs):
        created.append((args, kwargs))
        return SimpleNamespace(name="agent")

    called = {}

    def fake_host(factory, port, trust, co_dir=None, relay_url=None):
        called.update({"factory": factory, "port": port, "trust": trust, "relay_url": relay_url})

    monkeypatch.setattr(main_mod, "host", fake_host)
    monkeypatch.setattr(agent_mod, "create_coding_agent", fake_create)

    main_mod.start_server(port=1234, model="m1", max_iterations=7)

    assert called["port"] == 1234
    assert called["trust"] == "careful"
    assert called["relay_url"] is None
    assert callable(called["factory"])
    # factory should create agent with given params
    called["factory"]()
    assert created and created[0][1]["model"] == "m1"
