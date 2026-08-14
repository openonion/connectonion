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

from connectonion.cli.commands import email_commands
# The package __init__ re-exports the functions under the same names as their
# modules, so a dotted patch target resolves to the function; go through
# sys.modules to reach the real modules the handlers import from.
import connectonion.useful_tools.send_email
import connectonion.useful_tools.get_emails

_send_module = sys.modules["connectonion.useful_tools.send_email"]
_get_module = sys.modules["connectonion.useful_tools.get_emails"]


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


def test_an_empty_inbox_is_not_a_failure():
    """Listing nothing is an answer, not an error — must NOT raise."""
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_get_module, "get_emails", return_value=[]):
        email_commands.handle_email_inbox()


def test_a_successful_send_does_not_raise():
    ok = {"success": True, "message_id": "m1", "from": "x@mail.openonion.ai"}
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_send_module, "send_email", return_value=ok):
        email_commands.handle_email_send("a@b.com", "s", "m")
