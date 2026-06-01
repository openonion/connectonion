"""Tests for co_ai agent creation and server entrypoint."""
"""
LLM-Note: Tests for co ai agent main

What it tests:
- Co Ai Agent Main functionality

Components under test:
- Module: co_ai_agent_main
"""


from types import SimpleNamespace

import connectonion.cli.co_ai.agent as agent_mod
import connectonion.cli.co_ai.main as main_mod


def test_create_coding_agent(monkeypatch, tmp_path):
    class FakeLLM:
        model = "fake-model"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", lambda *a, **k: "BASE")
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "CTX")
    monkeypatch.setattr(agent_mod, "GLOBAL_CO_DIR", tmp_path / ".co")

    agent = agent_mod.create_coding_agent(model="fake", max_iterations=5, auto_approve=True)

    assert agent.name == "oo"
    assert agent.max_iterations == 5
    assert "BASE" in agent.system_prompt
    assert "CTX" in agent.system_prompt
    # FileTools is registered as a tool class
    assert "file_tools" in agent.tools._tools or any("file" in t.lower() for t in agent.tools._tools)
    assert "remote_login" not in agent.tools._tools
    assert "close_browser" in agent.tools._tools
    assert "send_qr_to_user" in agent.tools._tools
    assert "send_credentials_form_to_user" in agent.tools._tools
    assert "type_saved_login_credential" in agent.tools._tools
    assert "request_qr_scan" not in agent.tools._tools
    assert "request_login_credentials" not in agent.tools._tools
    assert "wait_for_manual_login" not in agent.tools._tools
    assert agent.browse is agent.tools.get_instance("browserautomation")
    assert agent.tools.get_instance("browserautomation")._headless is False
    assert agent_mod._enable_auto_approve in agent.events["after_user_input"]
    agent.current_session = {}
    agent_mod._enable_auto_approve(agent)
    assert agent.current_session["skip_tool_approval"] is True


def test_create_coding_agent_accepts_deploy_co_dir_and_headless_browser(monkeypatch, tmp_path):
    class FakeLLM:
        model = "fake-model"

    deploy_co_dir = tmp_path / ".co"
    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", lambda *a, **k: "BASE")
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "")

    agent = agent_mod.create_coding_agent(
        model="fake",
        max_iterations=9,
        co_dir=deploy_co_dir,
        browser_headless=True,
        browser_channel="chrome",
    )

    assert agent.co_dir == deploy_co_dir
    assert agent.tools.get_instance("browserautomation")._headless is True
    assert agent.tools.get_instance("browserautomation")._browser_channel == "chrome"


def test_create_coding_agent_accepts_custom_name(monkeypatch, tmp_path):
    class FakeLLM:
        model = "fake-model"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(agent_mod, "assemble_prompt", lambda *a, **k: "BASE")
    monkeypatch.setattr(agent_mod, "load_project_context", lambda *a, **k: "")

    agent = agent_mod.create_coding_agent(
        name="agent-4-linkedin",
        model="fake",
        co_dir=tmp_path / ".co",
    )

    assert agent.name == "agent-4-linkedin"


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
    assert "auto_approve" not in created[0][1]
