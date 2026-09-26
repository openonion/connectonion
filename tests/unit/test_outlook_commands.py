"""Tests for the `co outlook` CLI command layer."""
"""
LLM-Note: Tests for cli/commands/outlook_commands

What it tests:
- _outlook() credential/scope guard (prints 'co auth microsoft' hint, returns None)
- _parse_send_at relative (+30m/+2h) and ISO pass-through parsing
- _resolve_email_id resolves short numbers only inside the listing token they came with (#1754)
- handle_outlook_inbox/search freeze each listing, empty ones included; --json freezes none
- handle_outlook_send reads the body from stdin when message is '-'
- handle_outlook_reply forwards --attach files (and stdin bodies, and --at) to Outlook.reply, rejects missing/oversize files before replying, and keeps `at` third positional with attachments keyword-only

Components under test:
- Module: connectonion.cli.commands.outlook_commands
"""

import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest
import typer
from rich.console import Console

from connectonion.cli.commands import outlook_commands
from connectonion.cli.commands.outlook_commands import (
    _outlook,
    _parse_send_at,
    _resolve_email_id,
    handle_outlook_contact_add,
    handle_outlook_contact_list,
    handle_outlook_contact_search,
    handle_outlook_inbox,
    handle_outlook_reply,
    handle_outlook_search,
    handle_outlook_send,
)

CONNECTED_ENV = {
    "MICROSOFT_ACCESS_TOKEN": "test-token",
    "MICROSOFT_SCOPES": "Mail.Read,Mail.Send",
    "MICROSOFT_EMAIL": "aaron@example.com",
}

CONNECTED_CONTACT_ENV = {
    **CONNECTED_ENV,
    "MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send,Contacts.ReadWrite",
}


def sample_emails(n):
    return [{
        "id": f"msg-{i}",
        "from": f"sender{i}@example.com",
        "from_name": f"Sender {i}",
        "subject": f"Subject {i}",
        "date": "2026-07-06T10:00:00Z",
        "snippet": "Preview",
        "unread": i == 1,
    } for i in range(1, n + 1)]


class TestOutlookGuard:
    """_outlook() returns None with a hint when not connected."""

    def test_missing_access_token_exits_with_hint(self, capsys):
        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": "", "MICROSOFT_SCOPES": "Mail.Read"}, clear=False):
            with pytest.raises(typer.Exit):
                _outlook()

        output = capsys.readouterr().out
        assert "Microsoft account not connected" in output
        assert "co auth microsoft" in output

    def test_scopes_without_mail_exits_with_hint(self, capsys):
        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": "test-token", "MICROSOFT_SCOPES": "User.Read"}, clear=False):
            with pytest.raises(typer.Exit):
                _outlook()

        output = capsys.readouterr().out
        assert "Mail permission missing" in output
        assert "co auth microsoft" in output

    def test_mailbox_settings_scope_does_not_pass_as_mail(self, capsys):
        with patch.dict(
            os.environ,
            {"MICROSOFT_ACCESS_TOKEN": "test-token", "MICROSOFT_SCOPES": "MailboxSettings.Read"},
            clear=False,
        ):
            with pytest.raises(typer.Exit):
                _outlook()

        assert "Mail permission missing" in capsys.readouterr().out

    def test_connected_returns_outlook_instance(self):
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            result = _outlook()

        from connectonion.useful_tools.outlook import Outlook
        assert isinstance(result, Outlook)
        assert result._allow_external_attachments is True

    def test_contacts_scope_missing_exits_with_reconnect_hint(self, capsys):
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with pytest.raises(typer.Exit):
                _outlook(required_scope="Contacts.ReadWrite")

        output = capsys.readouterr().out
        assert "Contacts.ReadWrite" in output
        assert "co auth microsoft" in output


class TestParseSendAt:
    """_parse_send_at turns relative offsets into UTC ISO timestamps."""

    def test_plus_minutes(self):
        before = datetime.now(timezone.utc)
        result = _parse_send_at("+30m")
        after = datetime.now(timezone.utc)

        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert before + timedelta(minutes=30) - timedelta(seconds=2) <= parsed
        assert parsed <= after + timedelta(minutes=30) + timedelta(seconds=2)

    def test_plus_hours(self):
        before = datetime.now(timezone.utc)
        result = _parse_send_at("+2h")
        after = datetime.now(timezone.utc)

        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        assert before + timedelta(hours=2) - timedelta(seconds=2) <= parsed
        assert parsed <= after + timedelta(hours=2) + timedelta(seconds=2)

    def test_iso_string_passes_through(self):
        assert _parse_send_at("2026-07-06T15:30:00Z") == "2026-07-06T15:30:00Z"

    def test_invalid_unit_exits(self, capsys):
        with pytest.raises(typer.Exit):
            _parse_send_at("+5x")
        assert "Invalid --at value" in capsys.readouterr().out

    def test_missing_number_exits(self, capsys):
        with pytest.raises(typer.Exit):
            _parse_send_at("+m")
        assert "Invalid --at value" in capsys.readouterr().out

    def test_naive_iso_time_exits(self, capsys):
        with pytest.raises(typer.Exit):
            _parse_send_at("2026-07-06T15:30:00")
        assert "Invalid --at value" in capsys.readouterr().out

    def test_garbage_string_exits(self, capsys):
        with pytest.raises(typer.Exit):
            _parse_send_at("tomorrow")
        assert "Invalid --at value" in capsys.readouterr().out


class TestResolveEmailId:
    """_resolve_email_id maps short inbox numbers to Graph message ids."""

    @pytest.fixture(autouse=True)
    def _listings(self, tmp_path, monkeypatch):
        monkeypatch.setattr(outlook_commands, "LISTINGS", tmp_path / "outlook-listings")
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            yield

    def test_short_number_resolves_from_its_listing(self, tmp_path):
        from connectonion.cli.commands.gmail_listings import save_listing
        token = save_listing(tmp_path / "outlook-listings", "aaron@example.com", "messages",
                             ["msg-1", "msg-2"], provider="outlook")

        outlook = MagicMock()
        assert _resolve_email_id(outlook, "2", listing=token) == "msg-2"
        outlook.list_inbox.assert_not_called()

    def test_short_number_without_a_listing_is_refused_not_guessed(self):
        # The old fallback fetched a fresh inbox and took its row N — a
        # different list from the one the number was read off (#1754).
        from connectonion.cli.commands.gmail_listings import ListingError

        outlook = MagicMock()
        outlook.list_inbox.return_value = sample_emails(3)
        with pytest.raises(ListingError):
            _resolve_email_id(outlook, "2")
        outlook.list_inbox.assert_not_called()

    def test_long_numeric_id_passes_through(self, tmp_path, monkeypatch):
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", tmp_path / "missing.json")

        outlook = MagicMock()
        assert _resolve_email_id(outlook, "12345") == "12345"
        outlook.list_inbox.assert_not_called()

    def test_graph_message_id_passes_through(self, tmp_path, monkeypatch):
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", tmp_path / "missing.json")

        outlook = MagicMock()
        assert _resolve_email_id(outlook, "AAMkAGI2NGVhZTVlLTI=") == "AAMkAGI2NGVhZTVlLTI="
        outlook.list_inbox.assert_not_called()


class TestHandleOutlookInbox:
    """handle_outlook_inbox lists emails and remembers the numbering."""

    def test_freezes_the_numbering_under_a_listing_token(self, tmp_path, monkeypatch, capsys):
        listings = tmp_path / ".co" / "outlook-listings"
        monkeypatch.setattr(outlook_commands, "LISTINGS", listings)
        # Pin the interactive branch — CI has no tty, dev shells may force color.
        monkeypatch.setattr(outlook_commands, "console", Console(force_terminal=True, width=120))

        outlook = MagicMock()
        outlook.list_inbox.return_value = sample_emails(2)

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_inbox(last=2)

        [saved] = listings.glob("*.json")
        assert json.loads(saved.read_text())["ids"] == ["msg-1", "msg-2"]
        output = capsys.readouterr().out
        assert "Subject 1" in output
        assert f"co outlook read 1 --listing {saved.stem}" in output

    def test_piped_output_prints_plain_listing_with_its_token(self, tmp_path, monkeypatch, capsys):
        listings = tmp_path / ".co" / "outlook-listings"
        monkeypatch.setattr(outlook_commands, "LISTINGS", listings)
        # Pin the non-tty branch: scripts get the untruncated tool format.
        monkeypatch.setattr(outlook_commands, "console", Console(force_terminal=False))

        outlook = MagicMock()
        outlook.list_inbox.return_value = sample_emails(2)
        outlook._format_dicts.return_value = "Found 2 email(s) with full ids"

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_inbox(last=2)

        [saved] = listings.glob("*.json")
        assert json.loads(saved.read_text())["ids"] == ["msg-1", "msg-2"]
        output = capsys.readouterr().out
        assert "Found 2 email(s) with full ids" in output
        assert f"Listing: {saved.stem}" in output

    def test_empty_inbox_is_a_listing_with_no_rows(self, tmp_path, monkeypatch, capsys):
        # Leaving the older numbering in place is how `reply 1` reached an
        # email the user was not looking at (#1754).
        listings = tmp_path / ".co" / "outlook-listings"
        monkeypatch.setattr(outlook_commands, "LISTINGS", listings)

        outlook = MagicMock()
        outlook.list_inbox.return_value = []

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_inbox(last=10, unread=True)

        [saved] = listings.glob("*.json")
        assert json.loads(saved.read_text())["ids"] == []
        assert "no unread emails" in capsys.readouterr().out


class TestHandleOutlookRead:
    """Opening a message preserves unread state unless --mark-read was chosen."""

    def _outlook_mock(self, scopes=("Mail.ReadWrite", "Mail.Send", "Contacts.ReadWrite")):
        outlook = MagicMock()
        # The handler reads the write scope from the same selected record the
        # token came from, not from a per-field os.getenv.
        outlook._credentials.scopes = set(scopes)
        outlook.get_email_body.return_value = (
            "From: alice@example.com\nSubject: Hello\n--- Email Body ---\nThe body text"
        )
        return outlook

    def test_default_read_is_non_destructive(self, capsys):
        outlook = self._outlook_mock()
        with patch.dict(os.environ, CONNECTED_CONTACT_ENV, clear=False), \
             patch.object(outlook_commands, "_outlook", return_value=outlook):
            outlook_commands.handle_outlook_read("msg-123")

        outlook.mark_read.assert_not_called()
        assert "Unread state unchanged" in capsys.readouterr().out

    def test_explicit_mark_read_mutates_with_write_scope(self, capsys):
        outlook = self._outlook_mock()
        with patch.dict(os.environ, CONNECTED_CONTACT_ENV, clear=False), \
             patch.object(outlook_commands, "_outlook", return_value=outlook):
            outlook_commands.handle_outlook_read("msg-123", mark_read=True)

        outlook.mark_read.assert_called_once_with("msg-123")
        assert "Marked read" in capsys.readouterr().out

    def test_explicit_mark_read_explains_missing_scope(self, capsys):
        outlook = self._outlook_mock(scopes=("Mail.Read", "Mail.Send"))
        with patch.dict(os.environ, CONNECTED_ENV, clear=False), \
             patch.object(outlook_commands, "_outlook", return_value=outlook):
            outlook_commands.handle_outlook_read("msg-123", mark_read=True)

        outlook.mark_read.assert_not_called()
        assert "co auth microsoft" in capsys.readouterr().out


class TestHandleOutlookSend:
    """handle_outlook_send sends via the Outlook tool."""

    def test_message_dash_reads_stdin(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", io.StringIO("Body from stdin\nline two\n"))

        outlook = MagicMock()
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_send(to="bob@example.com", subject="Hi", message="-")

        outlook.send.assert_called_once_with(
            "bob@example.com", "Hi", "Body from stdin\nline two\n",
            cc=None, bcc=None, attachments=None, send_at=None,
        )
        assert "Sent" in capsys.readouterr().out

    def test_scheduled_send_prints_scheduled(self, capsys):
        outlook = MagicMock()
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_send(to="bob@example.com", subject="Hi", message="Later",
                                    at="2026-07-06T15:30:00Z")

        assert outlook.send.call_args.kwargs["send_at"] == "2026-07-06T15:30:00Z"
        output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
        assert "Scheduled" in output
        assert "2026-07-06T15:30:00Z" in output

    def test_not_connected_does_not_send(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("unused"))

        with patch.dict(os.environ, {"MICROSOFT_ACCESS_TOKEN": "", "MICROSOFT_SCOPES": ""}, clear=False):
            with patch("connectonion.useful_tools.outlook.Outlook") as mock_cls:
                with pytest.raises(typer.Exit):
                    handle_outlook_send(to="bob@example.com", subject="Hi", message="hello")

        mock_cls.assert_not_called()


class TestHandleOutlookReply:
    """handle_outlook_reply carries --attach files through to the Outlook tool."""

    def _reply(self, outlook, monkeypatch, **kwargs):
        cache = {"3": "msg-cached-3"}
        monkeypatch.setattr(outlook_commands, "_resolve_email_id",
                            lambda _outlook, email_id, listing=None: cache.get(email_id, ""))
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_reply(**kwargs)

    def test_without_attachments_replies_as_before(self, monkeypatch, capsys):
        outlook = MagicMock()
        self._reply(outlook, monkeypatch, email_id="3", message="Sounds good")

        outlook.reply.assert_called_once_with(
            "msg-cached-3", "Sounds good", attachments=None, send_at=None, cc=None, bcc=None,
        )
        output = capsys.readouterr().out
        assert "Replied" in output
        assert "Attached" not in output

    def test_forwards_repeated_attachments(self, tmp_path, monkeypatch, capsys):
        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF report")
        chart = tmp_path / "chart.png"
        chart.write_bytes(b"\x89PNG chart")

        outlook = MagicMock()
        self._reply(outlook, monkeypatch, email_id="3", message="Both attached",
                    attachments=[str(report), str(chart)])

        outlook.reply.assert_called_once_with(
            "msg-cached-3", "Both attached",
            attachments=[str(report), str(chart)], send_at=None, cc=None, bcc=None,
        )
        output = capsys.readouterr().out
        assert "Replied" in output
        assert "Attached: report.pdf, chart.png" in output

    def test_stdin_body_still_works_with_an_attachment(self, tmp_path, monkeypatch):
        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF report")
        monkeypatch.setattr(sys, "stdin", io.StringIO("Body from stdin\nline two\n"))

        outlook = MagicMock()
        self._reply(outlook, monkeypatch, email_id="3", message="-",
                    attachments=[str(report)])

        outlook.reply.assert_called_once_with(
            "msg-cached-3", "Body from stdin\nline two\n",
            attachments=[str(report)], send_at=None, cc=None, bcc=None,
        )

    def test_scheduled_reply_keeps_its_attachment(self, tmp_path, monkeypatch, capsys):
        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF report")

        outlook = MagicMock()
        self._reply(outlook, monkeypatch, email_id="3", message="Tomorrow",
                    attachments=[str(report)], at="2026-07-06T15:30:00Z")

        outlook.reply.assert_called_once_with(
            "msg-cached-3", "Tomorrow",
            attachments=[str(report)], send_at="2026-07-06T15:30:00Z", cc=None, bcc=None,
        )
        output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
        assert "Reply scheduled" in output
        assert "2026-07-06T15:30:00Z" in output
        assert "Attached: report.pdf" in output

    def test_missing_attachment_exits_without_replying(self, tmp_path, monkeypatch, capsys):
        outlook = MagicMock()

        with pytest.raises(typer.Exit):
            self._reply(outlook, monkeypatch, email_id="3", message="Attached",
                        attachments=[str(tmp_path / "gone.pdf")])

        outlook.reply.assert_not_called()
        assert "Attachment not found" in capsys.readouterr().out

    def test_oversize_attachments_exit_without_replying(self, tmp_path, monkeypatch, capsys):
        huge = tmp_path / "huge.bin"
        huge.write_bytes(b"")
        os.truncate(huge, 3_000_001)
        outlook = MagicMock()

        with pytest.raises(typer.Exit):
            self._reply(outlook, monkeypatch, email_id="3", message="Attached",
                        attachments=[str(huge)])

        outlook.reply.assert_not_called()
        assert "3MB" in capsys.readouterr().out

    def test_unknown_email_number_does_not_reply(self, tmp_path, monkeypatch, capsys):
        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF report")
        outlook = MagicMock()

        with pytest.raises(typer.Exit):
            self._reply(outlook, monkeypatch, email_id="99", message="Attached",
                        attachments=[str(report)])

        outlook.reply.assert_not_called()
        assert "No email #99" in capsys.readouterr().out


class TestHandleOutlookReplyPositionalCompatibility:
    """handle_outlook_reply's third positional argument is `at`, as it always was."""

    def _call(self, outlook, monkeypatch, *args, **kwargs):
        cache = {"3": "msg-cached-3"}
        monkeypatch.setattr(outlook_commands, "_resolve_email_id",
                            lambda _outlook, email_id, listing=None: cache.get(email_id, ""))
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_reply(*args, **kwargs)

    def test_legacy_third_positional_argument_still_schedules(self, monkeypatch, capsys):
        """The old handle_outlook_reply(id, message, at) call still schedules."""
        outlook = MagicMock()
        self._call(outlook, monkeypatch, "3", "See you then", "2026-07-06T15:30:00Z")

        outlook.reply.assert_called_once_with(
            "msg-cached-3", "See you then",
            attachments=None, send_at="2026-07-06T15:30:00Z", cc=None, bcc=None,
        )
        output = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
        assert "Reply scheduled" in output
        assert "Attached" not in output

    def test_attachments_cannot_be_passed_positionally(self, tmp_path, monkeypatch):
        """A fourth positional argument is a TypeError, not a silent schedule/attach swap."""
        report = tmp_path / "report.pdf"
        report.write_bytes(b"%PDF report")
        outlook = MagicMock()

        with pytest.raises(TypeError):
            self._call(outlook, monkeypatch, "3", "Attached", None, [str(report)])

        outlook.reply.assert_not_called()

    def test_handler_signature_keeps_at_third(self):
        """Guard the contract itself, so a future edit can't quietly reorder it."""
        import inspect

        params = inspect.signature(handle_outlook_reply).parameters
        assert list(params) == ["email_id", "message", "at", "attachments", "cc", "bcc", "listing"]
        for name in ("attachments", "cc", "bcc", "listing"):
            assert params[name].kind is inspect.Parameter.KEYWORD_ONLY


class TestHandleOutlookContacts:
    """Contact handlers delegate Graph work to Outlook and format the result."""

    def test_add_contact(self, capsys):
        outlook = MagicMock()
        outlook.add_contact.return_value = {
            "id": "contact-1",
            "name": "Zhou Yifei",
            "email": "zhou@example.com",
        }

        with patch.dict(os.environ, CONNECTED_CONTACT_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_contact_add(
                    "Zhou Yifei", "zhou@example.com"
                )

        outlook.add_contact.assert_called_once_with(
            "Zhou Yifei", "zhou@example.com"
        )
        output = capsys.readouterr().out
        assert "Saved contact" in output
        assert "Zhou Yifei" in output
        assert "zhou@example.com" in output

    def test_list_contacts_terminal_table(self, monkeypatch, capsys):
        monkeypatch.setattr(
            outlook_commands, "console",
            Console(force_terminal=True, width=120),
        )
        outlook = MagicMock()
        outlook.list_contacts.return_value = [{
            "id": "contact-1",
            "name": "Zhou Yifei",
            "email": "zhou@example.com",
        }]

        with patch.object(outlook_commands, "_outlook", return_value=outlook):
            handle_outlook_contact_list(last=25)

        outlook.list_contacts.assert_called_once_with(max_results=25)
        output = capsys.readouterr().out
        assert "Outlook contacts" in output
        assert "Zhou Yifei" in output
        assert "zhou@example.com" in output

    def test_search_contacts_empty_result(self, capsys):
        outlook = MagicMock()
        outlook.search_contacts.return_value = []

        with patch.object(outlook_commands, "_outlook", return_value=outlook):
            handle_outlook_contact_search("yifei", last=25)

        outlook.search_contacts.assert_called_once_with(
            "yifei", max_results=25
        )
        assert "no contacts matching" in capsys.readouterr().out


class TestCancelCannotReachTheInbox:
    """A number from one listing must not act on another listing's messages.

    Measured on a real mailbox: after `co outlook inbox`, `co outlook cancel 1`
    resolved row 1 of the *inbox* and deleted a received email, printing
    "✓ Canceled scheduled email 1" and exiting 0. Both listings numbered from 1
    into one cache file, and an empty `scheduled` returned without touching it,
    so the inbox numbering was still sitting there.
    """

    def test_an_inbox_number_is_not_a_scheduled_number(self, tmp_path, monkeypatch):
        cache = tmp_path / "outlook_last_inbox.json"
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)
        outlook_commands._remember_listing("inbox", sample_emails(3))

        assert _resolve_email_id(MagicMock(), "1", expect="scheduled") == ""

    def test_cancel_refuses_rather_than_deleting_whatever_is_at_that_row(
            self, tmp_path, monkeypatch, capsys):
        cache = tmp_path / "outlook_last_inbox.json"
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)
        outlook_commands._remember_listing("inbox", sample_emails(3))
        outlook = MagicMock()
        monkeypatch.setattr(outlook_commands, "_outlook", lambda: outlook)

        with pytest.raises(typer.Exit) as exit_:
            outlook_commands.handle_outlook_cancel("1")

        assert exit_.value.exit_code == 1
        outlook.cancel_scheduled.assert_not_called()      # the whole point
        assert "co outlook scheduled" in capsys.readouterr().out

    def test_an_empty_scheduled_listing_clears_the_numbering(self, tmp_path, monkeypatch, capsys):
        # The early return used to leave the previous listing in place, which is
        # how a stale inbox number survived into `cancel`.
        cache = tmp_path / "outlook_last_inbox.json"
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)
        outlook_commands._remember_listing("inbox", sample_emails(3))
        outlook = MagicMock()
        outlook.get_scheduled.return_value = []
        monkeypatch.setattr(outlook_commands, "_outlook", lambda: outlook)

        outlook_commands.handle_outlook_scheduled()

        assert json.loads(cache.read_text()) == {"kind": "scheduled", "rows": {}}
        assert _resolve_email_id(MagicMock(), "1", expect="scheduled") == ""

    def test_a_scheduled_listing_numbers_its_own_rows(self, tmp_path, monkeypatch, capsys):
        cache = tmp_path / "outlook_last_inbox.json"
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)
        outlook = MagicMock()
        outlook.get_scheduled.return_value = [
            {"id": "draft-a", "to": "x@y.z", "subject": "s", "send_at": "2026-09-17T06:00:00Z"}]
        monkeypatch.setattr(outlook_commands, "_outlook", lambda: outlook)

        outlook_commands.handle_outlook_scheduled()

        assert _resolve_email_id(MagicMock(), "1", expect="scheduled") == "draft-a"

    def test_a_cache_from_an_older_version_is_not_a_scheduled_one(self, tmp_path, monkeypatch):
        # Upgrading must not turn every existing number into a scheduled one.
        cache = tmp_path / "outlook_last_inbox.json"
        cache.write_text(json.dumps({"1": "msg-old"}))
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)

        assert _resolve_email_id(MagicMock(), "1", expect="scheduled") == ""

    def test_with_no_listing_at_all_cancel_does_not_fall_back_to_the_inbox(
            self, tmp_path, monkeypatch):
        # The no-cache fallback fetches the inbox. For a scheduled number that
        # is the same data-loss path by another route.
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", tmp_path / "missing.json")
        outlook = MagicMock()
        outlook.list_inbox.return_value = sample_emails(3)

        assert _resolve_email_id(outlook, "1", expect="scheduled") == ""
        outlook.list_inbox.assert_not_called()


class TestCancelSaysWhatWentWrong:
    """A cancel that finds nothing explains itself instead of quoting HTTP."""

    @staticmethod
    def _gone(monkeypatch, outlook):
        from connectonion.provider_credentials import ProviderCredentialError

        def raise_404(_message_id):
            raise ProviderCredentialError(
                "provider_unavailable", "Microsoft Graph API error (HTTP 404).",
                "co outlook inbox", status=404)

        outlook.cancel_scheduled.side_effect = raise_404
        monkeypatch.setattr(outlook_commands, "_outlook", lambda: outlook)
        monkeypatch.setattr(outlook_commands, "_resolve_email_id",
                            lambda _o, i, expect="inbox": f"graph-id-{i}")

    def test_a_scheduled_email_that_is_gone_says_so_and_points_at_the_listing(
            self, monkeypatch, capsys):
        # Found on a real mailbox: `cancel 1` against a stale listing answered
        # "Microsoft Graph API error (HTTP 404). Next: co outlook inbox" — the
        # transport's word for it, and a next step with nothing to do with it.
        outlook = MagicMock()
        self._gone(monkeypatch, outlook)

        with pytest.raises(typer.Exit) as exit_:
            outlook_commands.handle_outlook_cancel("1")

        assert exit_.value.exit_code == 1
        captured = capsys.readouterr()
        said = captured.out + captured.err
        assert "already gone out" in said and "earlier listing" in said
        assert "HTTP 404" not in said
        assert "co outlook scheduled" in said

    def test_the_failure_is_on_stderr(self, monkeypatch, capsys):
        # Someone redirecting stdout to a file must collect the answer, not the
        # failure — the other verbs already keep that separation.
        outlook = MagicMock()
        self._gone(monkeypatch, outlook)

        with pytest.raises(typer.Exit):
            outlook_commands.handle_outlook_cancel("1")

        assert "not there any more" in capsys.readouterr().err

    def test_another_failure_is_not_dressed_up_as_a_missing_email(
            self, monkeypatch, capsys):
        # Only 404 means "gone". A 500 keeps its own words rather than being
        # explained away as a stale number — it falls through to the shared
        # handler, which reports it as itself.
        from connectonion.provider_credentials import ProviderCredentialError

        outlook = MagicMock()
        outlook.cancel_scheduled.side_effect = ProviderCredentialError(
            "provider_unavailable", "Microsoft Graph API error (HTTP 500).",
            "co outlook inbox", status=500)
        monkeypatch.setattr(outlook_commands, "_outlook", lambda: outlook)
        monkeypatch.setattr(outlook_commands, "_resolve_email_id",
                            lambda _o, i, expect="inbox": "graph-id")

        with pytest.raises(typer.Exit):
            outlook_commands.handle_outlook_cancel("1")

        said = capsys.readouterr()
        assert "HTTP 500" in said.err
        assert "already gone out" not in (said.out + said.err)


class TestContactPipedOutput:
    """Piped contact rows must be machine-readable."""

    def test_rows_are_really_tab_separated(self, monkeypatch, capsys):
        """Rich expands \\t into spaces — the docs promise tabs, so `cut -f2` must work."""
        monkeypatch.setattr(outlook_commands, "console", Console(force_terminal=False, width=120))

        outlook_commands._print_contacts(
            [{"id": "contact-1", "name": "Zhou Yifei", "email": "zhou@example.com"}],
            "contacts",
        )

        row = capsys.readouterr().out.splitlines()[0]
        assert row.split("\t") == ["Zhou Yifei", "zhou@example.com", "contact-1"]


class TestReplyUsesTheListingYouSaw:
    """A row number means a row of the listing whose token came with it (#1754).

    The saved numbering used to be one file that `inbox --json`, an empty search
    and an empty unread listing all left alone, with no expiry and no account.
    After new mail arrived, `reply 1` answered the CEO from yesterday's table
    although the listing on screen had a customer at the top.
    """

    @staticmethod
    def _mail(message_id, sender):
        return {"id": message_id, "from": sender, "from_name": sender, "subject": "s",
                "date": "2026-09-26T00:00:00Z", "unread": False}

    @pytest.fixture
    def outlook(self, tmp_path, monkeypatch):
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", tmp_path / ".co" / "outlook_last_inbox.json")
        monkeypatch.setattr(outlook_commands, "LISTINGS", tmp_path / ".co" / "outlook-listings")
        monkeypatch.setattr(outlook_commands, "console", Console(force_terminal=False, width=200))
        outlook = MagicMock()
        outlook.list_inbox.return_value = [self._mail("CEO", "ceo@corp.com")]
        outlook._format_dicts.side_effect = lambda emails: "\n".join(e["id"] for e in emails)
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                yield outlook

    @staticmethod
    def _token(output):
        return re.search(r"Listing: ([a-f0-9]{32})", output).group(1)

    def test_a_bare_number_after_a_json_listing_does_not_reply_to_an_older_one(self, outlook, capsys):
        handle_outlook_inbox(last=10)
        outlook.list_inbox.return_value = [self._mail("CUSTOMER", "customer@client.com"),
                                           self._mail("CEO", "ceo@corp.com")]
        handle_outlook_inbox(last=10, json_output=True)

        with pytest.raises(typer.Exit):
            handle_outlook_reply("1", "Thanks, invoice attached")

        outlook.reply.assert_not_called()
        assert "--listing" in capsys.readouterr().err

    def test_an_empty_search_does_not_leave_an_older_numbering_in_force(self, outlook, capsys):
        handle_outlook_inbox(last=10)
        outlook.list_search.return_value = []
        handle_outlook_search("nomatch")

        with pytest.raises(typer.Exit):
            handle_outlook_reply("1", "yes")

        outlook.reply.assert_not_called()

    def test_a_number_with_its_listing_replies_to_that_row(self, outlook, capsys):
        handle_outlook_inbox(last=10)
        token = self._token(capsys.readouterr().out)

        handle_outlook_reply("1", "yes", listing=token)

        assert outlook.reply.call_args.args[0] == "CEO"

    def test_a_listing_from_another_account_is_refused(self, outlook, capsys):
        handle_outlook_inbox(last=10)
        token = self._token(capsys.readouterr().out)

        with patch.dict(os.environ, {"MICROSOFT_EMAIL": "someone-else@example.com"}):
            with pytest.raises(typer.Exit):
                handle_outlook_reply("1", "yes", listing=token)

        outlook.reply.assert_not_called()

    def test_a_listing_expires(self, outlook, capsys, monkeypatch):
        import time
        handle_outlook_inbox(last=10)
        token = self._token(capsys.readouterr().out)
        later = time.time() + 16 * 60
        monkeypatch.setattr("connectonion.cli.commands.gmail_listings.time.time", lambda: later)

        with pytest.raises(typer.Exit):
            handle_outlook_reply("1", "yes", listing=token)

        outlook.reply.assert_not_called()

    def test_a_full_message_id_needs_no_listing(self, outlook):
        handle_outlook_reply("AAMkAGI2NGVhZTVlLTI=", "yes")

        assert outlook.reply.call_args.args[0] == "AAMkAGI2NGVhZTVlLTI="
