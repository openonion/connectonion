"""Tests for co_ai sub-agent registry."""
"""
LLM-Note: Tests for co ai agents registry

What it tests:
- Co Ai Agents Registry functionality

Components under test:
- Module: co_ai_agents_registry
"""


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
