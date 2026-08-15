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
        json_output=False,
        resume=None,
        acp=False,
        acp_mcp=False,
        state_dir=None,
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
        json_output=True,
        resume="session-id",
        acp=False,
        acp_mcp=False,
        state_dir=None,
    )


def test_ai_forwards_acp_mode():
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(app, ["ai", "--acp"])

    assert result.exit_code == 0
    handler.assert_called_once_with(
        prompt=None,
        port=8000,
        model=DEFAULT_MODEL,
        max_iterations=100,
        yolo=False,
        yolo_turns=100,
        json_output=False,
        resume=None,
        acp=True,
        acp_mcp=False,
        state_dir=None,
    )


def test_ai_forwards_explicit_acp_state_dir(tmp_path):
    state_dir = tmp_path / "acp-state"
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(
            app,
            ["ai", "--acp", "--state-dir", str(state_dir)],
        )

    assert result.exit_code == 0
    assert handler.call_args.kwargs["acp"] is True
    assert handler.call_args.kwargs["state_dir"] == state_dir


def test_ai_forwards_explicit_acp_mcp_authority():
    with patch("connectonion.cli.commands.ai_commands.handle_ai") as handler:
        result = runner.invoke(app, ["ai", "--acp", "--acp-mcp"])

    assert result.exit_code == 0
    assert handler.call_args.kwargs["acp"] is True
    assert handler.call_args.kwargs["acp_mcp"] is True


def test_ai_rejects_acp_with_one_shot_options():
    result = runner.invoke(app, ["ai", "task", "--acp"])

    assert result.exit_code == 2
    assert "--acp cannot be combined" in strip_ansi(result.output)


def test_ai_rejects_acp_mcp_without_acp():
    result = runner.invoke(app, ["ai", "--acp-mcp"])

    assert result.exit_code == 2
    assert "--acp-mcp requires --acp" in strip_ansi(result.output)


def test_ai_rejects_state_dir_without_acp(tmp_path):
    result = runner.invoke(
        app,
        ["ai", "--state-dir", str(tmp_path / "state")],
    )

    assert result.exit_code == 2
    assert "--state-dir requires --acp" in strip_ansi(result.output)


def test_ai_rejects_non_positive_yolo_turns():
    result = runner.invoke(
        app,
        ["ai", "task", "--yolo", "--yolo-turns", "0"],
    )

    assert result.exit_code != 0
    output = strip_ansi(result.output)
    assert "--yolo-turns" in output
    assert "1" in output
