"""Exercise the live CLI through the actual Jira HTTP client with synthetic responses."""
import json
from unittest.mock import patch
import httpx
from typer.testing import CliRunner
from connectonion.cli.main import app

def test_scoped_live_reads_make_only_get_requests(monkeypatch):
    for name, value in {"JIRA_URL": "https://example.atlassian.net", "JIRA_EMAIL": "test@example.com", "JIRA_API_TOKEN": "synthetic"}.items():
        monkeypatch.setenv(name, value)
    seen = []
    def get(url, **kwargs):
        seen.append(kwargs["params"]["jql"])
        return httpx.Response(200, request=httpx.Request("GET", url), json={
            "issues": [{"key": "ALPHA-1", "fields": {"summary": "Synthetic", "description": "Only test data",
                        "updated": "2026-01-02T00:00:00Z", "creator": {"displayName": "Sam"}}}]})
    with patch("connectonion.useful_tools.jira.httpx.get", side_effect=get):
        changed = CliRunner().invoke(app, ["jira", "changes", "--project", "ALPHA", "--issues", "ALPHA-1", "--since", "2026-01-01T00:00:00Z", "--json"])
        shown = CliRunner().invoke(app, ["jira", "show", "ALPHA-1", "--project", "ALPHA", "--json"])
    assert changed.exit_code == shown.exit_code == 0, changed.output + shown.output
    assert json.loads(changed.stdout)["items"][0]["version"] == json.loads(shown.stdout)["version"]
    assert all("project = ALPHA" in query and "ALPHA-1" in query for query in seen)
    assert json.loads(shown.stdout)["source"] == "jira:ALPHA-1"
