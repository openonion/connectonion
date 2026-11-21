"""Jira CLI experience: preserve data and guide a caller using only its output."""

import json
import re
import shlex
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.useful_tools.jira_checkpoint import SyncResult


pytestmark = pytest.mark.unit
runner = CliRunner()


def sync_result(**overrides):
    fields = dict(scope={"type": "project", "project": "ALPHA"}, mode="incremental",
                  issues_read=1, issues_mapped=1, net_new_records=1,
                  placement="/tmp/jira [draft]/daily/2026/11/06.jsonl",
                  checkpoint_result="advanced", rejections={}, error_code=None,
                  error_detail=None, exit_code=0)
    return SyncResult(**(fields | overrides))


@pytest.mark.parametrize("projects", [[], [{"key": "ALPHA", "name": "Alpha [draft]"}]])
def test_project_listing_names_one_next_command_even_when_empty(projects):
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        factory.return_value.project_items.return_value = projects
        result = runner.invoke(app, ["jira", "projects"])
    assert result.exit_code == 0, result.output
    assert result.output.count("Next:") == 1
    assert "co jira" in result.output
    if projects:
        assert "Alpha [draft]" in result.stdout
    else:
        assert "co env set JIRA_URL" not in result.output  # empty is not broken config


@pytest.mark.parametrize("overrides", [
    {}, {"issues_read": 0, "issues_mapped": 0, "net_new_records": 0,
         "checkpoint_result": "unchanged"},
    {"net_new_records": 0}, {"checkpoint_result": "recovered"},
])
def test_incremental_success_names_the_same_scope_and_paths(overrides):
    with patch("connectonion.useful_tools.jira_checkpoint.run_jira_sync", return_value=sync_result(**overrides)):
        result = runner.invoke(app, ["jira", "sync-inc", "--project", "ALPHA", "--issues", "ALPHA-1",
                                     "--output", "/tmp/jira [draft]", "--state", "/tmp/my state", "--no-history"])
    assert result.exit_code == 0, result.output
    assert result.output.count("Next:") == 1
    tip = result.output.split("Next:", 1)[1]
    for text in ("co jira sync-inc --project ALPHA", "--issues ALPHA-1",
                 "--output '/tmp/jira [draft]'", "--state '/tmp/my state'", "--no-history"):
        assert text in tip


@pytest.mark.parametrize("as_json", [False, True])
def test_hard_failure_names_recovery_once_without_generic_exit_two_tip(as_json):
    failure = sync_result(error_code="auth_failure", error_detail="Jira authentication failed.", exit_code=2)
    with patch("connectonion.useful_tools.jira_checkpoint.run_jira_sync", return_value=failure):
        result = runner.invoke(app, ["jira", "sync-inc", "--project", "ALPHA", *(["--json"] if as_json else [])])
    assert result.exit_code == 2
    if as_json:
        report = json.loads(result.stdout)
        assert report["exit_code"] == 2
        assert "co jira" in report["recovery_action"]
        assert result.stderr == ""
    else:
        assert result.output.count("Next:") == 1
        assert result.output.split("Next:", 1)[1].lstrip().startswith("co jira")


@pytest.mark.parametrize("as_json", [False, True])
def test_explicit_environment_is_retained_in_success_and_failure_tips(tmp_path, as_json):
    selected = tmp_path / "selected account.env"
    selected.write_text("", encoding="utf-8")
    args = ["--env-file", str(selected), "jira", "verify", *(["--json"] if as_json else [])]
    from connectonion.useful_tools.jira import JiraConfigError
    with patch("connectonion.cli.commands.jira_commands._jira", side_effect=JiraConfigError("JIRA_URL is not set.")):
        failed = runner.invoke(app, args)
    assert failed.exit_code == 1
    recovery = json.loads(failed.stdout)["recovery_action"] if as_json else failed.output
    assert f"co --env-file '{selected}' jira" in recovery
    if not as_json:
        with patch("connectonion.cli.commands.jira_commands._jira") as factory:
            factory.return_value.verify_connection.return_value = {"site_url": "https://example.atlassian.net", "displayName": "Reader"}
            success = runner.invoke(app, args)
        assert success.exit_code == 0
        assert f"co --env-file '{selected}' jira projects" in success.output


def test_explicit_account_does_not_rewrite_co_inside_user_paths(tmp_path):
    selected = tmp_path / "co account.env"
    selected.write_text("", encoding="utf-8")
    output, state = tmp_path / "co notes", tmp_path / "co state"
    with patch("connectonion.useful_tools.jira_checkpoint.run_jira_sync", return_value=sync_result()):
        result = runner.invoke(app, ["--env-file", str(selected), "jira", "sync-inc", "--project", "ALPHA",
                                     "--output", str(output), "--state", str(state)])
    assert result.exit_code == 0, result.output
    tip = result.stdout.split("Next:", 1)[1].strip()
    assert shlex.split(tip) == ["co", "--env-file", str(selected), "jira", "sync-inc", "--project", "ALPHA",
                               "--output", str(output), "--state", str(state)]


@pytest.mark.parametrize("code", ["checkpoint_corrupt", "checkpoint_mismatch", "source_yaml_conflict"])
def test_recovery_does_not_claim_full_resets_invalid_state_or_advise_deleting(code):
    failure = sync_result(error_code=code, error_detail="Existing source state needs inspection.", exit_code=2)
    with patch("connectonion.useful_tools.jira_checkpoint.run_jira_sync", return_value=failure):
        result = runner.invoke(app, ["jira", "sync-inc", "--project", "ALPHA", "--json"])
    recovery = json.loads(result.stdout)["recovery_action"]
    assert "delete" not in recovery.lower()
    assert "--full" not in recovery
    assert "co jira sync-inc --help" in recovery


@pytest.mark.parametrize("colour", [False, True])
def test_provider_text_and_paths_remain_literal_in_human_output(monkeypatch, colour):
    # Match audit.PERSON/AGENT: a harness's explicit TTY override takes
    # precedence over FORCE_COLOR in Rich, even in a colour-enabled runner.
    monkeypatch.delenv("TTY_COMPATIBLE", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color" if colour else "dumb")
    if colour:
        monkeypatch.setenv("FORCE_COLOR", "1")
    else:
        monkeypatch.setenv("NO_COLOR", "1")
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        factory.return_value.project_items.return_value = [{"key": "ALPHA", "name": "[red]literal[/red] :rocket:"}]
        result = runner.invoke(app, ["jira", "projects"], color=colour)
    plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
    assert "[red]literal[/red] :rocket:" in plain
    assert ("\x1b[" in result.output) is colour


@pytest.mark.parametrize("summary, expected", [(None, "(no summary)"), ("Fix :warning: [red]literal[/red]", "Fix :warning: [red]literal[/red]")])
def test_issue_summaries_do_not_crash_or_change_source_text(summary, expected):
    with patch("connectonion.cli.commands.jira_commands._jira") as factory:
        factory.return_value.issue_items.return_value = [{"key": "ALPHA-1", "fields": {"summary": summary}}]
        result = runner.invoke(app, ["jira", "issues", "ALPHA", "ALPHA-1"])
    assert result.exit_code == 0, result.output
    assert expected in result.stdout


def test_incremental_help_states_local_writes_and_full_cursor_behavior():
    result = runner.invoke(app, ["jira", "sync-inc", "--help"])
    words = " ".join(result.stdout.split())
    assert "Writes" in words
    assert "cursor unchanged" in words
    assert "--full does not" in words
    assert "F13FCAKE" not in words


def test_json_success_never_contains_styling_or_human_tips(monkeypatch):
    monkeypatch.setenv("FORCE_COLOR", "1")
    with patch("connectonion.useful_tools.jira_checkpoint.run_jira_sync", return_value=sync_result()):
        result = runner.invoke(app, ["jira", "sync-inc", "--project", "ALPHA", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["placement"].endswith("06.jsonl")
    assert "\x1b[" not in result.output
    assert "Next:" not in result.output
