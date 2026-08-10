from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]


def load_yaml(path):
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_public_action_is_composite_and_uses_the_machine_runner():
    action = load_yaml(ROOT / "action.yml")

    assert action["runs"]["using"] == "composite"
    assert action["outputs"]["comment-url"]
    assert any(
        "python -m connectonion.cli.github_action" in step.get("run", "")
        for step in action["runs"]["steps"]
    )
    review = next(step for step in action["runs"]["steps"] if step.get("id") == "review")
    assert set(review["env"]) == {
        "CO_ACTION_PR_NUMBER",
        "CO_ACTION_MODEL",
        "GH_TOKEN",
        "OPENONION_API_KEY",
    }
    assert action["inputs"]["openonion-api-key"]["required"] == "true"
    assert all(
        "OPENONION_API_KEY" not in step.get("env", {})
        for step in action["runs"]["steps"]
        if step.get("id") != "review"
    )
    setups = [step for step in action["runs"]["steps"] if "uses" in step]
    assert all(len(step["uses"].split("@", 1)[1].split()[0]) == 40 for step in setups)
    uv_setup = next(step for step in setups if "astral-sh/setup-uv" in step["uses"])
    assert uv_setup["with"]["version"] == "0.12.3"
    sync = next(step for step in action["runs"]["steps"] if "uv sync" in step.get("run", ""))
    assert "--frozen" in sync["run"] and "--no-dev" in sync["run"]
    assert "--no-sync" in review["run"]


def test_dogfood_is_manual_least_privilege_and_default_branch_only():
    path = ROOT / ".github" / "workflows" / "co-ai-review.yml"
    workflow = load_yaml(path)
    text = path.read_text(encoding="utf-8")

    assert list(workflow["on"]) == ["workflow_dispatch"]
    assert workflow["permissions"] == {
        "contents": "read",
        "pull-requests": "read",
        "checks": "read",
        "statuses": "read",
        "issues": "write",
    }
    assert "github.event.repository.default_branch" in workflow["jobs"]["review"]["if"]
    assert "pull_request_target" not in text
    assert "openonion-api-key: ${{ secrets.OPENONION_API_KEY }}" in text
    assert "env:\n          OPENONION_API_KEY" not in text
    assert workflow["jobs"]["review"]["timeout-minutes"] == "30"
    checkout = workflow["jobs"]["review"]["steps"][0]
    assert len(checkout["uses"].split("@", 1)[1].split()[0]) == 40
    assert checkout["with"]["ref"] == "${{ github.event.repository.default_branch }}"
