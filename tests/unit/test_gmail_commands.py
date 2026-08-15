"""Unit tests for connectonion/cli/commands/gmail_commands.py

Tests cover:
- _gmail() credential/scope guard (prints 'co auth google' hint, exits 1)
- _when() rendering of RFC 2822 Date headers, including missing/malformed ones
- inbox listing: table in a terminal, full-id text when piped, numbering cache
- _resolve_email_id() short-number resolution against the cache and the fallback
- read/reply/send/sent/search handlers
"""

import io
import json
import os
import re
import sys
from unittest.mock import MagicMock, patch

import pytest
import typer
from rich.console import Console

from connectonion.cli.commands import gmail_commands
from connectonion.cli.commands.gmail_commands import (
    _gmail,
    _resolve_email_id,
    _when,
    handle_gmail_inbox,
    handle_gmail_read,
    handle_gmail_reply,
    handle_gmail_search,
    handle_gmail_send,
    handle_gmail_sent,
)

CONNECTED_ENV = {
    "GOOGLE_SCOPES": "gmail.send,gmail.readonly,gmail.modify,calendar",
    "GOOGLE_ACCESS_TOKEN": "test-token",
    "GOOGLE_REFRESH_TOKEN": "test-refresh",
    "GOOGLE_EMAIL": "aaron@example.com",
}

READONLY_ENV = {**CONNECTED_ENV, "GOOGLE_SCOPES": "gmail.send,gmail.readonly,calendar"}


def sample_emails(n):
    return [{
        "id": f"msg-{i}",
        "from": f"Sender {i} <sender{i}@example.com>",
        "subject": f"Subject {i}",
        "date": "Sun, 26 Jul 2026 14:30:00 +0000",
        "snippet": f"Preview {i}",
        "unread": i == 1,
    } for i in range(1, n + 1)]


def plain(text):
    """Strip ANSI colour codes so assertions match what a user reads."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Never touch the real ~/.co/gmail_last_inbox.json."""
    monkeypatch.setattr(gmail_commands, "INBOX_CACHE", tmp_path / ".co" / "gmail_last_inbox.json")


class TestGmailGuard:
    """_gmail() exits with a hint when Google is not connected."""

    def test_missing_access_token_exits_with_hint(self, capsys):
        with patch.dict(os.environ, {"GOOGLE_ACCESS_TOKEN": "", "GOOGLE_SCOPES": "gmail.send"}, clear=False):
            with pytest.raises(typer.Exit):
                _gmail()

        output = capsys.readouterr().out
        assert "Google account not connected" in output
        assert "co auth google" in output

    def test_scopes_without_gmail_exits_with_hint(self, capsys):
        with patch.dict(os.environ, {"GOOGLE_ACCESS_TOKEN": "test-token", "GOOGLE_SCOPES": "calendar"}, clear=False):
            with pytest.raises(typer.Exit):
                _gmail()

        output = capsys.readouterr().out
        assert "Gmail permission missing" in output
        assert "co auth google" in output

    def test_readonly_without_send_exits_with_hint(self, capsys):
        """Gmail() needs gmail.send too — the guard must catch it, not traceback."""
        with patch.dict(
            os.environ,
            {"GOOGLE_ACCESS_TOKEN": "test-token", "GOOGLE_SCOPES": "gmail.readonly"},
            clear=False,
        ):
            with pytest.raises(typer.Exit):
                _gmail()

        assert "Gmail permission missing" in capsys.readouterr().out

    def test_send_without_readonly_exits_with_hint(self, capsys):
        with patch.dict(
            os.environ,
            {"GOOGLE_ACCESS_TOKEN": "test-token", "GOOGLE_SCOPES": "gmail.send"},
            clear=False,
        ):
            with pytest.raises(typer.Exit):
                _gmail()

        assert "Gmail permission missing" in capsys.readouterr().out

    def test_connected_returns_gmail_instance(self):
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            result = _gmail()

        from connectonion.useful_tools.gmail import Gmail
        assert isinstance(result, Gmail)

    def test_full_scope_urls_are_accepted(self):
        """`co auth google` may store scopes as full Google URLs."""
        urls = ("https://www.googleapis.com/auth/gmail.readonly "
                "https://www.googleapis.com/auth/gmail.send")
        with patch.dict(os.environ, {**CONNECTED_ENV, "GOOGLE_SCOPES": urls}, clear=False):
            from connectonion.useful_tools.gmail import Gmail
            assert isinstance(_gmail(), Gmail)


class TestWhen:
    """_when() renders Gmail's RFC 2822 Date header."""

    def test_formats_rfc2822_header(self):
        assert re.fullmatch(r"[A-Z][a-z]{2} \d{2} \d{2}:\d{2}", _when("Sun, 26 Jul 2026 14:30:00 +0000"))

    def test_keeps_month_and_day(self):
        assert _when("Sun, 26 Jul 2026 14:30:00 +0000").startswith("Jul")

    def test_missing_date_header_shows_raw_value(self):
        """_email_dicts() fills 'Unknown' when a message has no Date header."""
        assert _when("Unknown") == "Unknown"

    def test_malformed_date_shows_raw_value(self):
        assert _when("15 Jannuary 2024") == "15 Jannuary 2024"

    def test_empty_date_shows_raw_value(self):
        assert _when("") == ""

    def test_date_without_offset_still_renders(self):
        assert re.fullmatch(r"[A-Z][a-z]{2} \d{2} \d{2}:\d{2}", _when("Sun, 26 Jul 2026 14:30:00"))


class TestHandleGmailInbox:
    """Inbox listing renders a table and caches the numbering."""

    def test_empty_inbox_message(self, capsys):
        gmail = MagicMock()
        gmail.list_inbox.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox()

        assert "no emails" in capsys.readouterr().out

    def test_empty_inbox_writes_no_cache(self, capsys):
        """An empty listing must not clobber the numbering from the last one."""
        gmail = MagicMock()
        gmail.list_inbox.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=10, unread=True)

        assert not gmail_commands.INBOX_CACHE.exists()
        assert "no unread emails" in capsys.readouterr().out

    def test_table_and_cache(self, monkeypatch, capsys):
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=True, width=120))
        gmail = MagicMock()
        gmail.list_inbox.return_value = sample_emails(3)

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=3)

        output = capsys.readouterr().out
        assert "Subject 1" in output
        assert "co gmail read" in output
        cached = json.loads(gmail_commands.INBOX_CACHE.read_text())
        assert cached == {"1": "msg-1", "2": "msg-2", "3": "msg-3"}

    def test_flags_reach_the_tool(self):
        gmail = MagicMock()
        gmail.list_inbox.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=25, unread=True)

        gmail.list_inbox.assert_called_once_with(last=25, unread=True)

    def test_email_without_date_header_still_lists(self, monkeypatch, capsys):
        """A missing Date header must not take down the whole listing."""
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=True, width=120))
        emails = sample_emails(2)
        emails[0]["date"] = "Unknown"
        gmail = MagicMock()
        gmail.list_inbox.return_value = emails

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=2)

        output = capsys.readouterr().out
        assert "Subject 1" in output
        assert "Subject 2" in output

    def test_piped_output_carries_full_ids(self, monkeypatch, capsys):
        """Scripts and agents must get untruncated ids, not a numbered table."""
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=False, width=120))
        gmail = MagicMock()
        gmail.list_inbox.return_value = sample_emails(2)
        gmail._format_dicts.return_value = "ID: msg-1\nID: msg-2"

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=2)

        assert "msg-1" in capsys.readouterr().out
        gmail._format_dicts.assert_called_once()

    def test_piped_output_still_caches_numbering(self, monkeypatch, capsys):
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=False, width=120))
        gmail = MagicMock()
        gmail.list_inbox.return_value = sample_emails(2)
        gmail._format_dicts.return_value = "listing"

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=2)

        assert json.loads(gmail_commands.INBOX_CACHE.read_text()) == {"1": "msg-1", "2": "msg-2"}


class TestResolveEmailId:
    """Short numbers mean the last listing shown."""

    def write_cache(self, mapping):
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps(mapping))

    def test_number_resolves_through_cache(self):
        self.write_cache({"1": "msg-a", "2": "msg-b"})

        gmail = MagicMock()
        assert _resolve_email_id(gmail, "2") == "msg-b"
        gmail.list_inbox.assert_not_called()

    def test_full_id_passes_through(self):
        gmail = MagicMock()
        assert _resolve_email_id(gmail, "18f2c9d0a1b2c3d4") == "18f2c9d0a1b2c3d4"
        gmail.list_inbox.assert_not_called()

    def test_long_numeric_id_passes_through(self):
        """Gmail ids can be all digits — 5+ digits is an id, not a listing number."""
        gmail = MagicMock()
        assert _resolve_email_id(gmail, "12345") == "12345"
        gmail.list_inbox.assert_not_called()

    def test_number_missing_from_cache_returns_empty(self):
        """Refetching a differently numbered list would open the wrong email."""
        self.write_cache({"1": "msg-a"})

        gmail = MagicMock()
        assert _resolve_email_id(gmail, "7") == ""
        gmail.list_inbox.assert_not_called()

    def test_number_falls_back_to_list_inbox_without_cache(self):
        """First run of the session: no listing yet, so fetch one."""
        gmail = MagicMock()
        gmail.list_inbox.return_value = sample_emails(3)

        assert _resolve_email_id(gmail, "2") == "msg-2"

    def test_number_beyond_inbox_returns_empty(self):
        gmail = MagicMock()
        gmail.list_inbox.return_value = sample_emails(1)

        assert _resolve_email_id(gmail, "5") == ""

    def test_zero_returns_empty_without_fetching(self):
        gmail = MagicMock()
        assert _resolve_email_id(gmail, "0") == ""
        gmail.list_inbox.assert_not_called()

    def test_non_ascii_digits_are_not_listing_numbers(self):
        """Full-width digits can't index a listing; treat them as an id."""
        gmail = MagicMock()
        assert _resolve_email_id(gmail, "２") == "２"
        gmail.list_inbox.assert_not_called()


class TestHandleGmailRead:
    """Read is non-destructive unless both the flag and scope allow mutation."""

    def _gmail_mock(self):
        gmail = MagicMock()
        gmail.get_email_body.return_value = (
            "From: alice@example.com\nSubject: Hello\n--- Email Body ---\nThe body text"
        )
        return gmail

    def test_unresolvable_number_exits_with_hint(self, capsys):
        gmail = MagicMock()
        gmail.list_inbox.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with pytest.raises(typer.Exit):
                handle_gmail_read("4")

        assert "No email #4" in plain(capsys.readouterr().out)
        gmail.get_email_body.assert_not_called()

    def test_prints_header_and_body(self, capsys):
        gmail = self._gmail_mock()

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(gmail_commands, "_gmail", return_value=gmail):
                handle_gmail_read("18f2c9d0a1b2c3d4")

        gmail.get_email_body.assert_called_once_with("18f2c9d0a1b2c3d4")
        output = plain(capsys.readouterr().out)
        assert "alice@example.com" in output
        assert "The body text" in output

    def test_marks_read_with_modify_scope(self, capsys):
        gmail = self._gmail_mock()

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(gmail_commands, "_gmail", return_value=gmail):
                handle_gmail_read("18f2c9d0a1b2c3d4", mark_read=True)

        gmail.mark_read.assert_called_once_with("18f2c9d0a1b2c3d4")
        assert "Marked read" in plain(capsys.readouterr().out)

    def test_does_not_mark_read_without_modify_scope(self, capsys):
        """The API rejects the write on readonly+send tokens."""
        gmail = self._gmail_mock()

        with patch.dict(os.environ, READONLY_ENV, clear=False):
            with patch.object(gmail_commands, "_gmail", return_value=gmail):
                handle_gmail_read("18f2c9d0a1b2c3d4", mark_read=True)

        gmail.mark_read.assert_not_called()
        output = plain(capsys.readouterr().out)
        assert "Marked read" not in output
        assert "co auth google" in output

    def test_default_read_preserves_unread_state_even_with_modify_scope(self, capsys):
        gmail = self._gmail_mock()

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(gmail_commands, "_gmail", return_value=gmail):
                handle_gmail_read("18f2c9d0a1b2c3d4")

        gmail.mark_read.assert_not_called()
        assert "Unread state unchanged" in plain(capsys.readouterr().out)

    def test_resolves_listing_number_through_cache(self, capsys):
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps({"1": "msg-a", "2": "msg-b"}))
        gmail = self._gmail_mock()

        with patch.dict(os.environ, READONLY_ENV, clear=False):
            with patch.object(gmail_commands, "_gmail", return_value=gmail):
                handle_gmail_read("2")

        gmail.get_email_body.assert_called_once_with("msg-b")


class TestHandleGmailReply:

    def test_replies_to_cached_number(self, capsys):
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps({"1": "msg-a"}))
        gmail = MagicMock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_reply("1", "Sounds good")

        gmail.reply.assert_called_once_with("msg-a", "Sounds good")
        assert "Replied" in plain(capsys.readouterr().out)

    def test_message_dash_reads_stdin(self, monkeypatch):
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps({"1": "msg-a"}))
        monkeypatch.setattr(sys, "stdin", io.StringIO("Body from stdin\nline two\n"))
        gmail = MagicMock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_reply("1", "-")

        gmail.reply.assert_called_once_with("msg-a", "Body from stdin\nline two\n")

    def test_unresolvable_number_does_not_reply(self, capsys):
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps({"1": "msg-a"}))
        gmail = MagicMock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with pytest.raises(typer.Exit):
                handle_gmail_reply("9", "Sounds good")

        gmail.reply.assert_not_called()
        assert "No email #9" in plain(capsys.readouterr().out)


class TestHandleGmailSendAndSearch:

    def test_send_reports_recipient(self, capsys):
        gmail = MagicMock()

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(gmail_commands, "_gmail", return_value=gmail):
                handle_gmail_send("bob@example.com", "Hi", "hello")

        gmail.send.assert_called_once_with("bob@example.com", "Hi", "hello",
                                           cc=None, bcc=None, attachments=None)
        output = plain(capsys.readouterr().out)
        assert "bob@example.com" in output
        assert "Sent" in output

    def test_send_passes_cc_and_bcc(self):
        gmail = MagicMock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_send("bob@example.com", "Hi", "hello",
                              cc="carol@example.com", bcc="dan@example.com")

        assert gmail.send.call_args.kwargs == {"cc": "carol@example.com",
                                               "bcc": "dan@example.com",
                                               "attachments": None}

    def test_send_reads_stdin_body(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", io.StringIO("piped body"))
        gmail = MagicMock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_send("bob@example.com", "Hi", "-")

        assert gmail.send.call_args.args[2] == "piped body"

    def test_not_connected_does_not_send(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("unused"))

        with patch.dict(os.environ, {"GOOGLE_ACCESS_TOKEN": "", "GOOGLE_SCOPES": ""}, clear=False):
            with patch("connectonion.useful_tools.gmail.Gmail") as mock_cls:
                with pytest.raises(typer.Exit):
                    handle_gmail_send("bob@example.com", "Hi", "hello")

        mock_cls.assert_not_called()

    def test_search_empty_result(self, capsys):
        gmail = MagicMock()
        gmail.list_search.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_search("invoice", last=5)

        gmail.list_search.assert_called_once_with("invoice", max_results=5)
        assert "no emails matching" in capsys.readouterr().out

    def test_search_empty_result_writes_no_cache(self):
        gmail = MagicMock()
        gmail.list_search.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_search("invoice", last=5)

        assert not gmail_commands.INBOX_CACHE.exists()

    def test_search_results_share_the_inbox_numbering_contract(self, monkeypatch, capsys):
        """`co gmail read <#>` after a search must open the search hit."""
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=True, width=120))
        gmail = MagicMock()
        gmail.list_search.return_value = sample_emails(2)

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_search("invoice", last=2)

        assert json.loads(gmail_commands.INBOX_CACHE.read_text()) == {"1": "msg-1", "2": "msg-2"}
        assert "Subject 1" in capsys.readouterr().out


class TestHandleGmailSent:

    def test_prints_sent_listing(self, capsys):
        gmail = MagicMock()
        gmail.get_sent_emails.return_value = "Found 1 email(s):\n\n1.  From: me@example.com"

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(gmail_commands, "_gmail", return_value=gmail):
                handle_gmail_sent(last=5)

        gmail.get_sent_emails.assert_called_once_with(max_results=5)
        assert "me@example.com" in capsys.readouterr().out

    def test_sent_does_not_disturb_the_read_numbering(self, capsys):
        """Only inbox and search define what `read <#>` means."""
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps({"1": "msg-a"}))
        gmail = MagicMock()
        gmail.get_sent_emails.return_value = "Found 0 email(s):"

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_sent(last=5)

        assert json.loads(gmail_commands.INBOX_CACHE.read_text()) == {"1": "msg-a"}


class TestGmailSendAttachmentChecks:
    """The precheck, which exists so a bad path costs a message rather than a
    traceback after megabytes have been base64-encoded."""

    def test_a_missing_file_is_refused_before_the_api_is_touched(self, capsys):
        gmail = MagicMock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with pytest.raises(typer.Exit):
                handle_gmail_send("bob@example.com", "Hi", "hello",
                                  attachments=["/nope/missing.pdf"])

        assert "missing.pdf" in capsys.readouterr().out
        gmail.send.assert_not_called(), "nothing should reach Gmail after a bad path"

    def test_oversize_is_refused_against_gmails_limit_not_outlooks(self, tmp_path, capsys):
        """Borrowing Outlook's 3MB would refuse mail Gmail accepts. This file
        is over Graph's limit and well under Gmail's."""
        big = tmp_path / "deck.pdf"
        big.write_bytes(b"x" * 5_000_000)
        gmail = MagicMock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_send("bob@example.com", "Hi", "hello", attachments=[str(big)])

        gmail.send.assert_called_once()
        assert "exceed" not in capsys.readouterr().out

    def test_over_gmails_own_limit_is_refused(self, tmp_path, capsys):
        huge = tmp_path / "video.mov"
        huge.write_bytes(b"x" * 26_000_000)
        gmail = MagicMock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with pytest.raises(typer.Exit):
                handle_gmail_send("bob@example.com", "Hi", "hello", attachments=[str(huge)])

        assert "25MB" in capsys.readouterr().out
        gmail.send.assert_not_called()
