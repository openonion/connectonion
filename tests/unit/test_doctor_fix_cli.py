"""CLI contract for the explicit doctor repair mode."""

from click.utils import strip_ansi
from typer.testing import CliRunner

from connectonion.cli.main import app


runner = CliRunner()


def test_help_exposes_fix_and_explicit_noninteractive_approval():
    output = strip_ansi(runner.invoke(app, ["doctor", "--help"]).output)

    assert "--fix" in output
    assert "--yes" in output


def test_yes_without_fix_fails_closed():
    result = runner.invoke(app, ["doctor", "--yes"])

    assert result.exit_code == 2
    assert "--yes requires --fix" in result.output
