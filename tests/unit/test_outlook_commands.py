"""Tests for the `co outlook` CLI command layer."""
"""
LLM-Note: Tests for cli/commands/outlook_commands

What it tests:
- _outlook() credential/scope guard (prints 'co auth microsoft' hint, returns None)
- _parse_send_at relative (+30m/+2h) and ISO pass-through parsing
- _resolve_email_id short-number resolution via cache file and list_inbox fallback
- handle_outlook_inbox writes the {#: message_id} cache
- handle_outlook_send reads the body from stdin when message is '-'

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
        assert "Microsoft account not connected" in output
        assert "co auth microsoft" in output

    def test_connected_returns_outlook_instance(self):
        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            result = _outlook()

        from connectonion.useful_tools.outlook import Outlook
        assert isinstance(result, Outlook)

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

    def test_short_number_resolves_from_cache(self, tmp_path, monkeypatch):
        cache = tmp_path / "outlook_last_inbox.json"
        cache.write_text(json.dumps({"1": "msg-cached-1", "2": "msg-cached-2"}))
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)

        outlook = MagicMock()
        assert _resolve_email_id(outlook, "2") == "msg-cached-2"
        outlook.list_inbox.assert_not_called()

    def test_short_number_falls_back_to_list_inbox(self, tmp_path, monkeypatch):
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", tmp_path / "missing.json")

        outlook = MagicMock()
        outlook.list_inbox.return_value = sample_emails(3)
        assert _resolve_email_id(outlook, "2") == "msg-2"

    def test_short_number_beyond_inbox_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", tmp_path / "missing.json")

        outlook = MagicMock()
        outlook.list_inbox.return_value = sample_emails(1)
        assert _resolve_email_id(outlook, "5") == ""

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

    def test_writes_cache_mapping(self, tmp_path, monkeypatch, capsys):
        cache = tmp_path / ".co" / "outlook_last_inbox.json"
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)
        # Pin the interactive branch — CI has no tty, dev shells may force color.
        monkeypatch.setattr(outlook_commands, "console", Console(force_terminal=True, width=120))

        outlook = MagicMock()
        outlook.list_inbox.return_value = sample_emails(2)

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_inbox(last=2)

        assert json.loads(cache.read_text()) == {"1": "msg-1", "2": "msg-2"}
        output = capsys.readouterr().out
        assert "Subject 1" in output
        assert "co outlook read" in output

    def test_piped_output_prints_plain_listing_with_cache(self, tmp_path, monkeypatch, capsys):
        cache = tmp_path / ".co" / "outlook_last_inbox.json"
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)
        # Pin the non-tty branch: scripts get the untruncated tool format.
        monkeypatch.setattr(outlook_commands, "console", Console(force_terminal=False))

        outlook = MagicMock()
        outlook.list_inbox.return_value = sample_emails(2)
        outlook._format_dicts.return_value = "Found 2 email(s) with full ids"

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_inbox(last=2)

        assert json.loads(cache.read_text()) == {"1": "msg-1", "2": "msg-2"}
        assert "Found 2 email(s) with full ids" in capsys.readouterr().out

    def test_empty_inbox_prints_message_without_cache(self, tmp_path, monkeypatch, capsys):
        cache = tmp_path / ".co" / "outlook_last_inbox.json"
        monkeypatch.setattr(outlook_commands, "INBOX_CACHE", cache)

        outlook = MagicMock()
        outlook.list_inbox.return_value = []

        with patch.object(outlook_commands, "_outlook", return_value=outlook):
            handle_outlook_inbox(last=10, unread=True)

        assert not cache.exists()
        assert "no unread emails" in capsys.readouterr().out


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


class TestHandleOutlookContacts:
    """Contact handlers delegate Graph work to Outlook and format the result."""

    def test_add_contact(self, capsys):
        outlook = MagicMock()
        outlook.add_contact.return_value = {
            "id": "contact-1",
            "name": "Zhou Yifei",
            "email": "zhouyifei0428@gmail.com",
        }

        with patch.dict(os.environ, CONNECTED_CONTACT_ENV, clear=False):
            with patch.object(outlook_commands, "_outlook", return_value=outlook):
                handle_outlook_contact_add(
                    "Zhou Yifei", "zhouyifei0428@gmail.com"
                )

        outlook.add_contact.assert_called_once_with(
            "Zhou Yifei", "zhouyifei0428@gmail.com"
        )
        output = capsys.readouterr().out
        assert "Saved contact" in output
        assert "Zhou Yifei" in output
        assert "zhouyifei0428@gmail.com" in output

    def test_list_contacts_terminal_table(self, monkeypatch, capsys):
        monkeypatch.setattr(
            outlook_commands, "console",
            Console(force_terminal=True, width=120),
        )
        outlook = MagicMock()
        outlook.list_contacts.return_value = [{
            "id": "contact-1",
            "name": "Zhou Yifei",
            "email": "zhouyifei0428@gmail.com",
        }]

        with patch.object(outlook_commands, "_outlook", return_value=outlook):
            handle_outlook_contact_list(last=25)

        outlook.list_contacts.assert_called_once_with(max_results=25)
        output = capsys.readouterr().out
        assert "Outlook contacts" in output
        assert "Zhou Yifei" in output
        assert "zhouyifei0428@gmail.com" in output

    def test_search_contacts_empty_result(self, capsys):
        outlook = MagicMock()
        outlook.search_contacts.return_value = []

        with patch.object(outlook_commands, "_outlook", return_value=outlook):
            handle_outlook_contact_search("yifei", last=25)

        outlook.search_contacts.assert_called_once_with(
            "yifei", max_results=25
        )
        assert "no contacts matching" in capsys.readouterr().out
