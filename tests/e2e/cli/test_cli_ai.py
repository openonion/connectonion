"""CLI routing tests for `co ai` YOLO mode."""

from unittest.mock import patch

from click.utils import strip_ansi
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.core.usage import DEFAULT_MODEL

runner = CliRunner()


def test_ai_forwards_yolo_options():
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(
            app,
            ["ai", "task", "--yolo", "--yolo-turns", "4"],
        )

    assert result.exit_code == 0
    handler.assert_called_once_with(
        prompt="task",
        port=8000,
        model=DEFAULT_MODEL,
        max_iterations=100,
        yolo=True,
        yolo_turns=4,
        evaluate=False,
        json_output=False,
        resume=None,
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
        yolo=False,
        yolo_turns=100,
        evaluate=False,
        json_output=True,
        resume="session-id",
    )


def test_ai_eval_is_explicit_and_forwarded():
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(app, ["ai", "task", "--eval"])

    assert result.exit_code == 0
    assert handler.call_args.kwargs["evaluate"] is True


def test_ai_rejects_non_positive_yolo_turns():
    result = runner.invoke(
        app,
        ["ai", "task", "--yolo", "--yolo-turns", "0"],
    )

    assert result.exit_code != 0
    output = strip_ansi(result.output)
    assert "--yolo-turns" in output
    assert "1" in output
