"""`co outlook` flag routing: what the command hands the handler."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def test_outlook_inbox_forwards_a_window_and_json():
    with patch("connectonion.cli.commands.outlook_commands.handle_outlook_inbox") as handler:
        result = runner.invoke(app, ["outlook", "inbox", "--since", "30d", "--json"])
    assert result.exit_code == 0
    handler.assert_called_once_with(last=10, unread=False, since="30d", until=None,
                                    json_output=True)


def test_outlook_inbox_without_a_window_is_unchanged():
    """-n keeps its meaning; nobody's existing habit breaks."""
    with patch("connectonion.cli.commands.outlook_commands.handle_outlook_inbox") as handler:
        result = runner.invoke(app, ["outlook", "inbox", "-n", "25", "-u"])
    assert result.exit_code == 0
    handler.assert_called_once_with(last=25, unread=True, since=None, until=None,
                                    json_output=False)
