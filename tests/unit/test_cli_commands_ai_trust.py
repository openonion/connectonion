"""Tests for CLI ai and trust command handlers."""
"""
LLM-Note: Tests for cli commands ai trust

What it tests:
- Cli Commands Ai Trust functionality

Components under test:
- Module: cli_commands_ai_trust
"""


import connectonion.cli.commands.ai_commands as ai_mod
import connectonion.cli.commands.trust_commands as trust_mod
from connectonion.cli.co_ai.agent import GLOBAL_CO_DIR


def test_handle_ai_calls_start_server(monkeypatch):
    called = {}
    created = {}

    def fake_create_coding_agent(**kwargs):
        agent = object()
        created.update(kwargs)
        created["agent"] = agent
        return agent

    def fake_start_server(agent, **kwargs):
        called.update(kwargs)
        called["agent"] = agent

    monkeypatch.setattr("connectonion.cli.co_ai.agent.create_coding_agent", fake_create_coding_agent)
    monkeypatch.setattr("connectonion.cli.co_ai.main.start_server", fake_start_server)

    ai_mod.handle_ai(port=1111, model="m", max_iterations=3)

    assert called["port"] == 1111
    assert called["agent"] is created["agent"]
    assert created["model"] == "m"
    assert created["max_iterations"] == 3
    assert created["co_dir"] == GLOBAL_CO_DIR


def test_trust_commands_list_and_actions(tmp_path, monkeypatch):
    # Point CO_DIR at temp path and create lists
    monkeypatch.setattr(trust_mod, "CO_DIR", tmp_path)
    (tmp_path / "contacts.txt").write_text("c1\n", encoding="utf-8")
    (tmp_path / "whitelist.txt").write_text("w1\n", encoding="utf-8")
    (tmp_path / "blocklist.txt").write_text("b1\n", encoding="utf-8")

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
