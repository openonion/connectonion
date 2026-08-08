"""CLI contract for the explicit doctor repair mode."""

from typer.testing import CliRunner

from connectonion.cli.main import app


runner = CliRunner()


def test_help_exposes_fix_and_explicit_noninteractive_approval():
    output = runner.invoke(app, ["doctor", "--help"]).output

    assert "--fix" in output
    assert "--yes" in output
    assert "--json" in output


def test_yes_without_fix_fails_closed():
    result = runner.invoke(app, ["doctor", "--yes"])

    assert result.exit_code == 2
    assert "--yes requires --fix" in result.output
