"""The three tip gaps found by the cli-skill-design tip test (#1011).

1. Piped listings printed no tip — the `if console.is_terminal:` guard hid the
   next step from exactly the AI/script callers who need it.
2. The idempotency retry hint said "the same command" without restating it, so
   there was nothing in the output to reconstruct the retry from.
3. The stale-number message stopped one step short of the goal ("run co gmail
   to refresh" — then what?).

Under pytest the Rich console is not a terminal, so calling the handlers here
exercises the piped branch — the branch a human tester never sees.
"""

import sys
from unittest.mock import Mock, patch

import pytest
import typer

from connectonion.cli.commands import email_commands, gdrive_commands, gmail_commands, outlook_commands
import connectonion.useful_tools.send_email  # noqa: F401 — the real modules, past the package re-exports
import connectonion.useful_tools.get_emails  # noqa: F401

_send_module = sys.modules["connectonion.useful_tools.send_email"]
_get_module = sys.modules["connectonion.useful_tools.get_emails"]

EMAILS = [{"id": "18f2a", "from": "a@x.com", "subject": "hi", "date": "Unknown", "unread": False}]


def test_gmail_piped_listing_still_names_the_next_step(tmp_path, capsys):
    gmail = Mock()
    gmail._format_dicts.return_value = "1. a@x.com  hi  ID: 18f2a"
    with patch.object(gmail_commands, "INBOX_CACHE", tmp_path / "gmail.json"):
        gmail_commands._print_listing(gmail, EMAILS, "inbox")
    assert "Read one with: co gmail read <#>" in capsys.readouterr().out


def test_outlook_piped_listing_still_names_the_next_step(tmp_path, capsys):
    outlook = Mock()
    outlook._format_dicts.return_value = "1. a@x.com  hi  ID: 18f2a"
    with patch.object(outlook_commands, "INBOX_CACHE", tmp_path / "outlook.json"):
        outlook_commands._print_listing(outlook, EMAILS, "inbox")
    assert "Read one with: co outlook read <#>" in capsys.readouterr().out


def test_outlook_piped_scheduled_still_names_the_next_step(tmp_path, capsys):
    outlook = Mock()
    outlook.get_scheduled.return_value = [
        {"id": "s1", "to": "a@x.com", "subject": "hi", "send_at": "2026-08-15T10:00:00Z"},
    ]
    with patch.object(outlook_commands, "INBOX_CACHE", tmp_path / "outlook.json"), \
         patch.object(outlook_commands, "_outlook", return_value=outlook):
        outlook_commands.handle_outlook_scheduled()
    assert "Cancel one with: co outlook cancel <#>" in capsys.readouterr().out


def test_gdrive_piped_listing_still_names_the_next_step(tmp_path, capsys):
    files = [{"id": "f1", "name": "report.pdf", "type": "application/pdf", "size": "10", "modified": ""}]
    with patch.object(gdrive_commands, "LIST_CACHE", tmp_path / "gdrive.json"):
        gdrive_commands._print_listing(files, "drive")
    assert "Download one with: co gdrive get <#>" in capsys.readouterr().out


def test_retry_hint_restates_the_full_command(capsys):
    failed = {
        "success": False, "error": "Request timed out.",
        "retryable": True, "idempotency_key": "k-123", "request_id": "r-1",
    }
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_send_module, "send_email", return_value=failed):
        with pytest.raises(typer.Exit):
            email_commands.handle_email_send("bob@example.com", "Hello", "Body text")
    out = capsys.readouterr().out
    # The whole command, not just the flag — the output is all a fresh agent has.
    assert "co email send bob@example.com Hello 'Body text' --idempotency-key k-123" in out


def test_stale_gmail_number_names_the_step_after_the_refresh(capsys):
    with patch.object(gmail_commands, "_gmail", return_value=Mock()), \
         patch.object(gmail_commands, "_resolve_email_id", return_value=""):
        with pytest.raises(typer.Exit):
            gmail_commands.handle_gmail_read("3")
    assert "run co gmail, then co gmail read <#>" in capsys.readouterr().out


def test_stale_email_id_names_the_step_after_the_refresh(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_get_module, "get_emails", return_value=[]):
        with pytest.raises(typer.Exit):
            email_commands.handle_email_read("999")
    out = " ".join(capsys.readouterr().out.split())  # Rich wraps at 80 columns
    assert "run co email inbox, then co email read <#>" in out


def test_send_success_names_the_sent_listing(capsys):
    ok = {"success": True, "message_id": "m1", "from": "x@mail.openonion.ai"}
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_send_module, "send_email", return_value=ok):
        email_commands.handle_email_send("a@b.com", "s", "m")
    assert "co email sent" in capsys.readouterr().out
