"""Jira discovery and read errors remain useful after retiring exports."""
import json
from unittest.mock import patch
import pytest
from typer.testing import CliRunner
from connectonion.cli.main import app

@pytest.mark.parametrize("projects", [[], [{"key": "ALPHA", "name": "Alpha [draft]"}]])
def test_projects_names_read_only_next(projects):
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        factory.return_value.project_items.return_value = projects
        result = CliRunner().invoke(app, ["jira", "projects"])
    assert result.exit_code == 0, result.output
    assert result.output.count("Next:") == 1
    assert "sync" not in result.output

@pytest.mark.parametrize("leaf", ["sync", "sync-inc"])
def test_retired_exports_are_not_commands(leaf):
    result = CliRunner().invoke(app, ["jira", leaf, "--help"])
    assert result.exit_code == 2

def test_projects_json_preserves_unicode():
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        factory.return_value.project_items.return_value = [{"key": "ALPHA", "name": "中文项目"}]
        result = CliRunner().invoke(app, ["jira", "projects", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["projects"][0]["name"] == "中文项目"

def test_discovery_failure_is_not_a_successful_empty_list():
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        factory.return_value.project_items.side_effect = ValueError("Rate limit")
        result = CliRunner().invoke(app, ["jira", "projects", "--json"])
    assert result.exit_code == 1
    assert "projects" not in json.loads(result.stdout)

@pytest.mark.parametrize("leaf", ["verify", "projects", "issues", "changes", "show"])
def test_help_never_loads_credentials(leaf):
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        result = CliRunner().invoke(app, ["jira", leaf, "--help"])
    assert result.exit_code == 0, result.output
    assert "Example:" in result.output
    factory.assert_not_called()
