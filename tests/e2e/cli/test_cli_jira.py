"""Real CLI/collector/record/checkpoint flow with only the HTTP boundary replaced."""

import copy
import json
import re

import httpx
import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app

pytestmark = [pytest.mark.e2e, pytest.mark.cli]


@pytest.fixture
def jira_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://test.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "fixture@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fixture-only-token")
    issue = {"id": "1", "key": "ALPHA-1", "fields": {
        "summary": "Original title", "created": "2026-11-01T00:00:00Z",
        "updated": "2026-11-06T00:00:00Z", "description": "Evidence text",
    }}
    state = {"issue": issue, "warnings": False, "queries": []}

    def get(url, **kwargs):
        if url.endswith("/myself"):
            body = {"accountId": "fixture-account", "displayName": "Fixture Reader"}
        else:
            assert url.endswith("/search/jql"), url
            jql = kwargs["params"]["jql"]
            state["queries"].append(jql)
            if state["warnings"] or re.search(r'updated >= "[^\"]*T', jql):
                body = {"issues": [], "warningMessages": ["Invalid query date"]}
            else:
                body = {"issues": [copy.deepcopy(state["issue"])], "isLast": True}
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))

    monkeypatch.setattr("connectonion.useful_tools.jira.httpx.get", get)
    output, checkpoints = tmp_path / "source", tmp_path / "state"
    arguments = ["jira", "sync-inc", "--project", "ALPHA", "--output", str(output),
                 "--state", str(checkpoints), "--no-history", "--json"]
    return state, output, checkpoints, arguments


def test_first_repeat_and_changed_import_retain_versions(jira_cli):
    state, output, checkpoints, arguments = jira_cli
    runner = CliRunner()
    first = runner.invoke(app, arguments)
    assert first.exit_code == 0, first.output
    assert json.loads(first.stdout)["net_new_records"] == 1
    again = runner.invoke(app, arguments)
    assert again.exit_code == 0, again.output
    assert json.loads(again.stdout)["net_new_records"] == 0
    state["issue"]["fields"].update(summary="Updated title", updated="2026-11-06T00:01:00Z")
    changed = runner.invoke(app, arguments)
    assert changed.exit_code == 0, changed.output
    assert json.loads(changed.stdout)["net_new_records"] == 1
    records = [json.loads(line) for path in output.glob("daily/*/*/*.jsonl") for line in path.read_text().splitlines()]
    assert [record["title"] for record in records] == ["Original title", "Updated title"]
    assert len({record["id"] for record in records}) == 1
    assert "fixture-only-token" not in "".join(path.read_text() for path in output.rglob("*") if path.is_file())


def test_provider_warning_is_failure_and_preserves_checkpoint(jira_cli):
    state, output, checkpoints, arguments = jira_cli
    runner = CliRunner()
    assert runner.invoke(app, arguments).exit_code == 0
    before = {path: path.read_bytes() for path in checkpoints.glob("checkpoints/*.json")}
    state["warnings"] = True
    failed = runner.invoke(app, arguments)
    assert failed.exit_code == 2, failed.output
    assert json.loads(failed.stdout)["error_code"] == "fetch_failed"
    assert failed.stderr == ""
    assert {path: path.read_bytes() for path in before} == before


def test_full_read_does_not_reset_a_corrupted_checkpoint(jira_cli):
    _, _, checkpoints, arguments = jira_cli
    runner = CliRunner()
    assert runner.invoke(app, arguments).exit_code == 0
    checkpoint = next(checkpoints.glob("checkpoints/*.json"))
    checkpoint.write_text("not json", encoding="utf-8")
    failed = runner.invoke(app, [*arguments, "--full"])
    assert failed.exit_code == 2
    report = json.loads(failed.stdout)
    assert report["error_code"] == "checkpoint_corrupt"
    assert "--full" not in report["recovery_action"]
    assert "delete" not in report["error"].lower()
    assert "--full" not in report["error"]
    assert checkpoint.read_text() == "not json"


def test_selected_sync_cannot_overwrite_incremental_source_metadata(jira_cli):
    _, output, checkpoints, arguments = jira_cli
    runner = CliRunner()
    assert runner.invoke(app, arguments).exit_code == 0
    before = {path: path.read_bytes() for root in (output, checkpoints) for path in root.rglob("*") if path.is_file()}
    selected = runner.invoke(app, ["jira", "sync", "ALPHA", "ALPHA-1", "--output", str(output), "--no-history", "--json"])
    assert selected.exit_code == 1, selected.output
    assert "separate" in json.loads(selected.stdout)["error"]
    assert {path: path.read_bytes() for path in before} == before
    repeated = runner.invoke(app, arguments)
    assert repeated.exit_code == 0, repeated.output
    assert json.loads(repeated.stdout)["net_new_records"] == 0
