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


def test_project_override_is_discovered_once_and_used_by_task(tmp_path, monkeypatch):
    subagents = importlib.import_module("connectonion.useful_plugins.subagents")
    project = tmp_path / "project"
    definition = project / ".co/agents/explore/AGENT.md"
    definition.parent.mkdir(parents=True)
    definition.write_text("---\nname: explore\ndescription: Project exploration\n"
                          "model: co/project-model\nmax_iterations: 3\n"
                          "tools: [read_file]\n---\nProject-only instructions.\n")
    nested = project / "src/nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "isolated-home")

    discovered = [item for item in subagents._discover_all_agents() if item["name"] == "explore"]
    assert discovered == [{"name": "explore", "description": "Project exploration", "location": "project"}]
    assert Path(subagents._load_agent("explore")["path"]) == definition
    created = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            created.update(kwargs)

        def input(self, prompt):
            created["prompt"] = prompt
            return "project result"

    monkeypatch.setattr("connectonion.core.agent.Agent", FakeAgent)
    assert subagents.task(None, "inspect this project", "explore") == "project result"
    assert created["model"] == "co/project-model"
    assert created["max_iterations"] == 3
    assert created["system_prompt"] == "Project-only instructions."
    assert [tool.__name__.rsplit(".", 1)[-1] for tool in created["tools"]] == ["read_file"]
    assert created["prompt"] == "inspect this project"
