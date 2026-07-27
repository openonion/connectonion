"""CLI routing tests for `co ai` YOLO mode."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app


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
        model="co/gemini-3.6-flash",
        max_iterations=100,
        yolo=True,
        yolo_turns=4,
    )


def test_ai_rejects_non_positive_yolo_turns():
    result = runner.invoke(
        app,
        ["ai", "task", "--yolo", "--yolo-turns", "0"],
    )

    assert result.exit_code != 0
    assert "--yolo-turns" in result.output
    assert "1" in result.output
