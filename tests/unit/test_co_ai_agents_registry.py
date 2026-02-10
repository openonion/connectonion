"""Tests for co_ai sub-agent registry."""

import connectonion.cli.co_ai.agents.registry as reg


def test_get_subagent(monkeypatch):
    class FakeLLM:
        model = "fake"

    monkeypatch.setattr("connectonion.core.agent.create_llm", lambda *a, **k: FakeLLM())

    agent = reg.get_subagent("explore")
    assert agent is not None
    assert agent.name.startswith("oo-")
    assert agent.max_iterations == reg.SUBAGENTS["explore"]["max_iterations"]

    assert reg.get_subagent("unknown") is None
