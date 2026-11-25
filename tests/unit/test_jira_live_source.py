"""DD-081 live Jira CLI contract replaces the local-snapshot REM adapter tests."""
import json
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.useful_tools.jira import Jira


def issue(key="ALPHA-1", updated="2026-01-02T00:00:00+00:00"):
    return {"key": key, "fields": {"summary": "计划 [draft]", "description": "Read me",
            "updated": updated, "creator": {"displayName": "Sam", "accountId": "person-1"}}}


def test_changes_explicit_scope_and_pure_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".co").mkdir()
    client = Mock(_base="https://example.atlassian.net")
    client.changed_issues.return_value = [issue()]
    with patch("connectonion.cli.commands.jira_commands._jira", return_value=client):
        result = CliRunner().invoke(app, ["jira", "changes", "--project", "ALPHA", "--issues", "ALPHA-1",
                                          "--since", "2026-01-01T00:00:00Z", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["items"][0]["id"] == "ALPHA-1"
    assert len(data["items"][0]["version"]) == 64
    assert data["scope"] == {"project": "ALPHA", "issues": ["ALPHA-1"]}
    assert "Next:" in result.stderr
    assert list(tmp_path.iterdir()) == [tmp_path / ".co"]
    assert not list((tmp_path / ".co").iterdir())
    client.changed_issues.assert_called_once_with("ALPHA", "2026-01-01T00:00:00Z", issue_keys=["ALPHA-1"])


def test_show_live_citation_and_changed_version():
    client = Mock(_base="https://example.atlassian.net")
    client.show_issue.side_effect = [issue(), issue(updated="2026-01-03T00:00:00Z")]
    with patch("connectonion.cli.commands.jira_commands._jira", return_value=client):
        first = CliRunner().invoke(app, ["jira", "show", "ALPHA-1", "--json"])
        second = CliRunner().invoke(app, ["jira", "show", "ALPHA-1", "--json"])
    one, two = json.loads(first.stdout), json.loads(second.stdout)
    assert one["source"] == "jira:ALPHA-1"
    assert one["text"] == "Read me"
    assert one["author"] == "Sam"
    assert one["link"] == "https://example.atlassian.net/browse/ALPHA-1"
    assert one["version"] != two["version"]


@pytest.mark.parametrize("error", ["Authentication failed", "Rate limit 429", "Issue deleted or inaccessible", "Incomplete pagination"])
def test_source_failures_do_not_emit_partial_json(error):
    client = Mock()
    client.show_issue.side_effect = ValueError(error)
    with patch("connectonion.cli.commands.jira_commands._jira", return_value=client):
        result = CliRunner().invoke(app, ["jira", "show", "ALPHA-1", "--json"])
    assert result.exit_code == 1
    assert not result.stdout
    assert error in result.stderr


def test_empty_changes_is_success():
    client = Mock(_base="https://example.atlassian.net")
    client.changed_issues.return_value = []
    with patch("connectonion.cli.commands.jira_commands._jira", return_value=client):
        result = CliRunner().invoke(app, ["jira", "changes", "--project", "ALPHA", "--since", "2026-01-01T00:00Z", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"] == []


@pytest.mark.parametrize("since", ["wrong", "2026-01-01", "2999-01-01T00:00Z"])
def test_bad_since_never_loads_credentials(since):
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        result = CliRunner().invoke(app, ["jira", "changes", "--project", "ALPHA", "--since", since, "--json"])
    assert result.exit_code != 0
    factory.assert_not_called()


def test_missing_project_never_loads_credentials():
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        result = CliRunner().invoke(app, ["jira", "changes", "--since", "2026-01-01T00:00Z", "--json"])
    assert result.exit_code == 2
    factory.assert_not_called()


@pytest.mark.parametrize("key", ["BETA-1", "ALPHA-2"])
def test_api_scope_escape_is_rejected(key):
    client = object.__new__(Jira)
    with patch.object(client, "scoped_issues", return_value=[issue(key)]):
        with pytest.raises(ValueError, match="outside the selected scope"):
            client.changed_issues("ALPHA", "2026-01-01T00:00Z", issue_keys=["ALPHA-1"])


def test_exact_since_filters_older_rows_and_keeps_boundary():
    client = object.__new__(Jira)
    with patch.object(client, "scoped_issues", return_value=[issue(updated="2026-01-01T00:00:01Z"), issue("ALPHA-2", "2026-01-01T00:00:02Z")]):
        rows = client.changed_issues("ALPHA", "2026-01-01T00:00:02Z")
    assert [row["key"] for row in rows] == ["ALPHA-2"]


def test_show_rejects_cross_project_before_network():
    client = object.__new__(Jira)
    with patch.object(client, "_get") as get:
        with pytest.raises(ValueError, match="does not belong"):
            client.show_issue("BETA-1", project_key="ALPHA")
    get.assert_not_called()


@pytest.mark.parametrize("command", ["changes", "show"])
def test_live_help_has_no_source_access(command):
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        result = CliRunner().invoke(app, ["jira", command, "--help"])
    assert result.exit_code == 0
    assert "Example:" in result.output
    assert "Next:" in result.output
    factory.assert_not_called()
