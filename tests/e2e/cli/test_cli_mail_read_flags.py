"""Every mailbox uses the same safe-by-default read contract."""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app


runner = CliRunner()


@pytest.mark.parametrize(("command", "handler"), [
    ("email", "connectonion.cli.commands.email_commands.handle_email_read"),
    ("outlook", "connectonion.cli.commands.outlook_commands.handle_outlook_read"),
])
def test_read_preserves_unread_state_by_default(command, handler):
    with patch(handler) as read:
        result = runner.invoke(app, [command, "read", "3"])

    assert result.exit_code == 0
    read.assert_called_once_with("3", mark_read=False)


@pytest.mark.parametrize(("command", "handler"), [
    ("email", "connectonion.cli.commands.email_commands.handle_email_read"),
    ("outlook", "connectonion.cli.commands.outlook_commands.handle_outlook_read"),
])
def test_mark_read_is_explicit_and_uniform(command, handler):
    with patch(handler) as read:
        result = runner.invoke(app, [command, "read", "3", "--mark-read"])

    assert result.exit_code == 0
    read.assert_called_once_with("3", mark_read=True)
