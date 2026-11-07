import json

from connectonion.cli.commands import jira_commands


class FakeJira:
    def verify_connection(self):
        return {"site_url": "https://example.atlassian.net", "accountId": "a1", "displayName": "Ada"}

    def issue_items(self, project, keys):
        assert project == "ALPHA"
        assert keys == {"ALPHA-1"}
        return [{"key": "ALPHA-1", "fields": {"summary": "Selected issue", "issuetype": {"name": "Task"}}}]

    def write_source_yaml(self, directory, project, keys):
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "source.yaml"
        target.write_text("driver: jira\n", encoding="utf-8")
        return target


def test_verify_json_is_safe(monkeypatch, capsys):
    monkeypatch.setattr(jira_commands, "_jira", lambda: FakeJira())
    jira_commands.handle_jira_verify(as_json=True)
    assert json.loads(capsys.readouterr().out) == {
        "account": "https://example.atlassian.net", "account_id": "a1", "display_name": "Ada"
    }


def test_sync_json_writes_only_selected_issue(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(jira_commands, "_jira", lambda: FakeJira())
    jira_commands.handle_jira_sync("ALPHA", ["ALPHA-1"], output_dir=tmp_path, as_json=True)
    result = json.loads(capsys.readouterr().out)
    assert result["issues"] == result["mapped"] == result["appended"] == 1
    assert (tmp_path / "source.yaml").exists()
