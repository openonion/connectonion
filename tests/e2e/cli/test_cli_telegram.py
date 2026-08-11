"""CLI routing tests for ``co telegram send``."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def test_telegram_send_routes_chat_and_message():
    with patch(
        "connectonion.cli.commands.telegram_commands.handle_telegram_send"
    ) as handler:
        result = runner.invoke(
            app,
            ["telegram", "send", "@openonion", "Deployment complete"],
        )

    assert result.exit_code == 0
    handler.assert_called_once_with("@openonion", "Deployment complete")


def test_telegram_help_lists_send():
    result = runner.invoke(app, ["telegram", "--help"])

    assert result.exit_code == 0
    assert "send" in result.output


def test_telegram_send_requires_chat_and_message():
    with patch(
        "connectonion.cli.commands.telegram_commands.handle_telegram_send"
    ) as handler:
        result = runner.invoke(app, ["telegram", "send", "@openonion"])

    assert result.exit_code != 0
    handler.assert_not_called()


def test_telegram_appears_in_common_help():
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "telegram" in result.output
