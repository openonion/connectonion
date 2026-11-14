"""Import parser feedback must not depend on Typer's internal core.click alias."""

import json
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from connectonion.cli.commands import import_feedback
from connectonion.cli.main import app


PRIVATE_VALUE = "synthetic-private-invalid-argument"


@pytest.fixture(autouse=True)
def no_core_click_alias(monkeypatch):
    """Remove the feature's alias access without altering Typer's own runtime globals."""
    facade = SimpleNamespace(core=SimpleNamespace(), echo=typer.echo, Exit=typer.Exit)
    monkeypatch.setattr(import_feedback, "typer", facade)


def _invalid_args(source, kind):
    group = ["jira"] if source == "jira" else ["onenote", "source"]
    selected = ["ALPHA", "ALPHA-1"] if source == "jira" else ["nb-test", "section-test", "page-test"]
    if kind == "missing":
        return [*group, "sync", selected[0]]
    if kind == "unknown-option":
        return [*group, "sync", *selected, "--" + PRIVATE_VALUE]
    if kind == "bad-value":
        return ([*group, "sync", *selected, "--history=" + PRIVATE_VALUE] if source == "jira" else
                [*group, "pages", *selected[:2], "--limit", PRIVATE_VALUE])
    return [*group, PRIVATE_VALUE if kind == "unknown-command" else "--" + PRIVATE_VALUE]


@pytest.mark.parametrize("source", ["jira", "onenote"])
@pytest.mark.parametrize("kind", ["missing", "unknown-option", "bad-value", "unknown-command", "group-option"])
@pytest.mark.parametrize("as_json", [True, False], ids=["json", "human"])
def test_usage_error_without_core_click_is_safe(source, kind, as_json, caplog):
    args = [*_invalid_args(source, kind), *(["--json"] if as_json else [])]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2, result.output
    assert PRIVATE_VALUE not in result.stdout + result.stderr + caplog.text
    assert "Traceback" not in result.output and "AttributeError" not in result.output
    if as_json:
        report = json.loads(result.stdout)
        assert result.stderr == ""
        assert report["source"] == source and report["exit_code"] == 2
        assert report["error_code"] == "invalid_input" and report["scope"]["command"]
        assert report["recovery_action"].endswith("--help")
    else:
        assert result.stdout == ""
        assert source in result.stderr and result.stderr.count("Next:") == 1


@pytest.mark.parametrize("args", [
    ["jira", "--help"], ["jira", "sync", "--help"],
    ["onenote", "source", "--help"], ["onenote", "source", "sync", "--help"],
])
def test_help_without_core_click_still_exits_zero(args):
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "Usage:" in result.stdout and "--help" in result.stdout
    assert not result.stderr and "Traceback" not in result.stdout


def test_unexpected_parser_error_is_not_misclassified(monkeypatch):
    def fail_parse(self, ctx, args):
        raise RuntimeError("Unexpected parser defect")
    monkeypatch.setattr(typer.core.TyperCommand, "parse_args", fail_parse)
    result = CliRunner().invoke(app, ["jira", "sync", "ALPHA", "ALPHA-1", "--json"])
    assert isinstance(result.exception, RuntimeError)
    assert result.stdout == "" and "invalid_input" not in result.output
