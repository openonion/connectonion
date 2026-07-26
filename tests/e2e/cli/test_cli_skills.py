"""CLI routing tests for `co skills`."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def test_skills_link_routes_force():
    with patch("connectonion.cli.commands.skills_commands.handle_skills_link") as handler:
        result = runner.invoke(app, ["skills", "link", "--force"])

    assert result.exit_code == 0
    handler.assert_called_once_with(force=True)


def test_skills_link_defaults_to_no_force():
    with patch("connectonion.cli.commands.skills_commands.handle_skills_link") as handler:
        result = runner.invoke(app, ["skills", "link"])

    assert result.exit_code == 0
    handler.assert_called_once_with(force=False)


def test_skills_help_lists_link():
    result = runner.invoke(app, ["skills", "--help"])

    assert result.exit_code == 0
    assert "link" in result.output
