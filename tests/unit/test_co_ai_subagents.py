"""Regression coverage for co ai's single live subagent source."""

import importlib
from pathlib import Path

import connectonion


def test_packaged_subagents_have_one_source_of_truth():
    package_root = Path(connectonion.__file__).parent
    shadows = [
        package_root / "cli" / "co_ai" / "agents" / "registry.py",
        package_root / "cli" / "co_ai" / "prompts" / "agents" / "explore.md",
        package_root / "cli" / "co_ai" / "prompts" / "agents" / "plan.md",
    ]

    assert [path for path in shadows if path.exists()] == []


def test_task_builds_explore_agent_from_live_definition(monkeypatch):
    subagents = importlib.import_module("connectonion.useful_plugins.subagents")
    expected_path = Path(subagents.__file__).parent / "builtin_agents" / "explore" / "AGENT.md"
    monkeypatch.setattr(subagents, "_get_agent_paths", lambda _name: [expected_path])

    config = subagents._load_agent("explore")
    assert config is not None
    assert Path(config["path"]) == expected_path

    created = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            created.update(kwargs)

        def input(self, prompt):
            created["prompt"] = prompt
            return "explored"

    monkeypatch.setattr("connectonion.core.agent.Agent", FakeAgent)

    result = subagents.task(None, "map the repository", "explore")

    assert result == "explored"
    assert created["name"] == "sub-explore"
    assert created["max_iterations"] == 15
    assert created["prompt"] == "map the repository"
    assert "READ-ONLY MODE" in created["system_prompt"]
    assert [tool.__name__.rsplit(".", 1)[-1] for tool in created["tools"]] == [
        "glob",
        "grep",
        "read_file",
    ]
