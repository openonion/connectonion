"""Every co email failure must exit non-zero, like its gmail/outlook siblings.

Every failure path in email_commands printed an error and returned normally,
so the process exited 0 and `co email send … && next` ran `next` after a
failed send. `co gmail`/`co outlook` exit 1 in the same situations — two
sibling command groups disagreed about what a failure is (#1012).

A legitimately empty result is not a failure: an empty inbox listing still
exits 0. Asking for a specific email that does not exist is one — the command
did not deliver what was asked.
"""

import sys
from unittest.mock import patch

import pytest
import typer
from click.utils import strip_ansi
from typer.testing import CliRunner

# The package __init__ re-exports the functions under the same names as their
# modules, so a dotted patch target resolves to the function; go through
# sys.modules to reach the real modules the handlers import from.
import connectonion.useful_tools.get_emails  # noqa: F401
import connectonion.useful_tools.send_email  # noqa: F401
from connectonion.cli.commands import email_commands
from connectonion.cli.main import app

_send_module = sys.modules["connectonion.useful_tools.send_email"]
_get_module = sys.modules["connectonion.useful_tools.get_emails"]
runner = CliRunner()


def test_missing_auth_exits_nonzero():
    with patch.object(email_commands, "load_api_key", return_value=None):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_send("a@b.com", "s", "m")
    assert exc_info.value.exit_code == 1


def test_failed_send_exits_nonzero():
    failed = {"success": False, "error": "insufficient credits"}
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_send_module, "send_email", return_value=failed):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_send("a@b.com", "s", "m")
    assert exc_info.value.exit_code == 1


def test_reading_a_missing_email_exits_nonzero():
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_get_module, "get_emails", return_value=[]):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_read("999")
    assert exc_info.value.exit_code == 1


def test_reading_preserves_unread_state_by_default(capsys):
    email = {"id": "7", "from": "a@b.com", "subject": "Hi",
             "timestamp": "now", "message": "body"}
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_get_module, "get_emails", return_value=[email]), \
         patch.object(_get_module, "mark_read") as mark_read:
        email_commands.handle_email_read("7")

    mark_read.assert_not_called()
    assert "Unread state unchanged" in capsys.readouterr().out


def test_explicit_mark_read_mutates_the_agent_mailbox(capsys):
    email = {"id": "7", "from": "a@b.com", "subject": "Hi",
             "timestamp": "now", "message": "body"}
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_get_module, "get_emails", return_value=[email]), \
         patch.object(_get_module, "mark_read") as mark_read:
        email_commands.handle_email_read("7", mark_read=True)

    mark_read.assert_called_once_with("7")
    assert "Marked read" in capsys.readouterr().out


def test_an_empty_inbox_is_not_a_failure():
    """Listing nothing is an answer, not an error — must NOT raise."""
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_get_module, "get_emails", return_value=[]):
        email_commands.handle_email_inbox()


def test_inbox_rejects_more_than_one_backend_page_before_calling_it():
    with patch.object(_get_module, "get_emails") as get_emails:
        result = runner.invoke(app, ["email", "inbox", "--last", "1001"])

    assert result.exit_code == 2
    output = strip_ansi(result.output)
    assert "--last" in output
    assert "1<=x<=1000" in output
    get_emails.assert_not_called()


def test_inbox_forwards_the_page_size_and_offset():
    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(_get_module, "get_emails", return_value=[]) as get_emails:
        result = runner.invoke(
            app,
            ["email", "inbox", "--last", "1000", "--offset", "2000"],
        )

    assert result.exit_code == 0
    get_emails.assert_called_once_with(last=1000, offset=2000, address=None)


def test_a_successful_send_does_not_raise():
    ok = {"success": True, "message_id": "m1", "from": "x@mail.openonion.ai"}
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_send_module, "send_email", return_value=ok):
        email_commands.handle_email_send("a@b.com", "s", "m")
