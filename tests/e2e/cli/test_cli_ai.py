"""CLI routing tests for the bounded `co ai` Full access mode."""

from pathlib import Path
from unittest.mock import patch

from click.utils import strip_ansi
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.core.usage import DEFAULT_MODEL

runner = CliRunner()


def test_ai_forwards_full_access_options():
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(
            app,
            ["ai", "task", "--full-access", "--full-access-turns", "4"],
        )

    assert result.exit_code == 0
    handler.assert_called_once_with(
        prompt="task",
        port=8000,
        model=DEFAULT_MODEL,
        max_iterations=100,
        full_access=True,
        full_access_turns=4,
        evaluate=False,
        json_output=False,
        resume=None,
        invite_code=None,
        invite_code_file=None,
    )


def test_ai_forwards_json_and_resume_options():
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(
            app,
            ["ai", "task", "--json", "--resume", "session-id"],
        )

    assert result.exit_code == 0
    handler.assert_called_once_with(
        prompt="task",
        port=8000,
        model=DEFAULT_MODEL,
        max_iterations=100,
        full_access=False,
        full_access_turns=100,
        evaluate=False,
        json_output=True,
        resume="session-id",
        invite_code=None,
        invite_code_file=None,
    )


def test_ai_rejects_non_positive_full_access_turns():
    result = runner.invoke(
        app,
        ["ai", "task", "--full-access", "--full-access-turns", "0"],
    )

    assert result.exit_code != 0
    output = strip_ansi(result.output)
    assert "--full-access-turns" in output
    assert "1" in output


def test_ai_eval_is_explicit_and_forwarded():
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(app, ["ai", "task", "--eval"])

    assert result.exit_code == 0
    assert handler.call_args.kwargs["evaluate"] is True


def test_ai_forwards_invocation_invite_options():
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(
            app,
            ["ai", "--invite-code-file", "/private/invite"],
        )

    assert result.exit_code == 0
    assert handler.call_args.kwargs["invite_code"] is None
    assert handler.call_args.kwargs["invite_code_file"] == Path("/private/invite")
