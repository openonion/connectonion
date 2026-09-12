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
    handle_gmail_draft_attach,
    handle_gmail_draft_create,
    handle_gmail_draft_list,
    handle_gmail_draft_preview,
    handle_gmail_draft_remove,
    handle_gmail_draft_replace,
    handle_gmail_draft_send,
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


from connectonion.cli.commands.gmail_listings import save_listing, ListingError


def mail_mock():
    client = MagicMock()
    client.get_account_email.return_value = 'one@example.test'
    client._draft_attachment_budget.return_value = 25_000_000
    return client


def cached_rows(path):
    files = list((path.parent / 'gmail-listings').glob('*.json'))
    data = json.loads(max(files, key=lambda p: p.stat().st_mtime_ns).read_text())
    return {str(i): value for i, value in enumerate(data['ids'], 1)}


def freeze(gmail, ids, family='messages'):
    return save_listing(gmail_commands.INBOX_CACHE.parent / 'gmail-listings',
                        gmail.get_account_email(), family, ids)


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Never touch the real ~/.co/gmail_last_inbox.json."""
    monkeypatch.setattr(gmail_commands, "INBOX_CACHE", tmp_path / ".co" / "gmail_last_inbox.json")
    monkeypatch.setattr(gmail_commands, "DRAFT_CACHE", tmp_path / ".co" / "gmail_last_drafts.json")


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

    def test_readonly_without_send_can_read(self, capsys):
        """A deliberately restricted read grant must remain usable."""
        with patch.dict(
            os.environ,
            {"GOOGLE_ACCESS_TOKEN": "test-token", "GOOGLE_SCOPES": "gmail.readonly"},
            clear=False,
        ):
            assert _gmail() is not None

        assert "Gmail permission missing" not in capsys.readouterr().out

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

    def test_draft_write_without_compose_or_modify_exits_with_fix(self, capsys):
        with patch.dict(os.environ, READONLY_ENV, clear=False):
            with pytest.raises(typer.Exit):
                _gmail(require_draft_write=True)

        output = plain(capsys.readouterr().out)
        assert "draft permission missing" in output
        assert "co auth google" in output


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
        gmail = mail_mock()
        gmail.list_inbox.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox()

        assert "no emails" in capsys.readouterr().out

    def test_empty_inbox_clears_numbers(self, capsys):
        """An empty listing must not retain older rows."""
        gmail = mail_mock()
        gmail.list_inbox.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=10, unread=True)

        assert cached_rows(gmail_commands.INBOX_CACHE) == {}
        assert "no unread emails" in capsys.readouterr().out

    def test_table_and_cache(self, monkeypatch, capsys):
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=True, width=120))
        gmail = mail_mock()
        gmail.list_inbox.return_value = sample_emails(3)

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=3)

        output = capsys.readouterr().out
        assert "Subject 1" in output
        assert "co gmail read" in output
        cached = cached_rows(gmail_commands.INBOX_CACHE)
        assert cached == {"1": "msg-1", "2": "msg-2", "3": "msg-3"}

    def test_flags_reach_the_tool(self):
        gmail = mail_mock()
        gmail.list_inbox.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=25, unread=True)

        gmail.list_inbox.assert_called_once_with(last=25, unread=True)

    def test_email_without_date_header_still_lists(self, monkeypatch, capsys):
        """A missing Date header must not take down the whole listing."""
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=True, width=120))
        emails = sample_emails(2)
        emails[0]["date"] = "Unknown"
        gmail = mail_mock()
        gmail.list_inbox.return_value = emails

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=2)

        output = capsys.readouterr().out
        assert "Subject 1" in output
        assert "Subject 2" in output

    def test_piped_output_carries_full_ids(self, monkeypatch, capsys):
        """Scripts and agents must get untruncated ids, not a numbered table."""
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=False, width=120))
        gmail = mail_mock()
        gmail.list_inbox.return_value = sample_emails(2)
        gmail._format_dicts.return_value = "ID: msg-1\nID: msg-2"

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=2)

        assert "msg-1" in capsys.readouterr().out
        gmail._format_dicts.assert_called_once()

    def test_piped_output_still_caches_numbering(self, monkeypatch, capsys):
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=False, width=120))
        gmail = mail_mock()
        gmail.list_inbox.return_value = sample_emails(2)
        gmail._format_dicts.return_value = "listing"

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_inbox(last=2)

        assert cached_rows(gmail_commands.INBOX_CACHE) == {"1": "msg-1", "2": "msg-2"}


class TestResolveEmailId:
    def test_number_resolves_only_through_its_frozen_listing(self):
        gmail = mail_mock()
        token = freeze(gmail, ['msg-a', 'msg-b'])
        assert _resolve_email_id(gmail, '2', token) == 'msg-b'
        gmail.list_inbox.assert_not_called()

    @pytest.mark.parametrize('value', ['18f2c9d0a1b2c3d4', '12345', '２'])
    def test_full_id_bypasses_cache_and_account_request(self, value):
        gmail = mail_mock()
        assert _resolve_email_id(gmail, value) == value
        gmail.get_account_email.assert_not_called()
        gmail.list_inbox.assert_not_called()

    @pytest.mark.parametrize('value', ['0', '1', '7'])
    def test_bare_numbers_never_fetch_a_new_inbox(self, value):
        gmail = mail_mock()
        with pytest.raises(ListingError, match='--listing'):
            _resolve_email_id(gmail, value)
        gmail.list_inbox.assert_not_called()

    def test_a_row_outside_the_listing_fails(self):
        gmail = mail_mock()
        token = freeze(gmail, ['msg-a'])
        with pytest.raises(ListingError):
            _resolve_email_id(gmail, '7', token)
        gmail.list_inbox.assert_not_called()


class TestHandleGmailRead:
    """Read is non-destructive unless both the flag and scope allow mutation."""

    def _gmail_mock(self):
        gmail = mail_mock()
        gmail.get_email_body.return_value = (
            "From: alice@example.com\nSubject: Hello\n--- Email Body ---\nThe body text"
        )
        return gmail

    def test_unresolvable_number_exits_with_hint(self, capsys):
        gmail = mail_mock()
        gmail.list_inbox.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with pytest.raises(typer.Exit):
                handle_gmail_read("4")

        assert "requires --listing" in plain(capsys.readouterr().out)
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
                with pytest.raises(typer.Exit) as exc:
                    handle_gmail_read("18f2c9d0a1b2c3d4", mark_read=True)
                assert exc.value.exit_code == 1

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
                handle_gmail_read("2", listing=freeze(gmail, ["msg-a", "msg-b"]))

        gmail.get_email_body.assert_called_once_with("msg-b")


class TestHandleGmailReply:

    def test_replies_to_cached_number(self, capsys):
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps({"1": "msg-a"}))
        gmail = mail_mock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_reply("1", "Sounds good", listing=freeze(gmail, ["msg-a"]))

        gmail.reply.assert_called_once_with("msg-a", "Sounds good")
        assert "Replied" in plain(capsys.readouterr().out)

    def test_message_dash_reads_stdin(self, monkeypatch):
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps({"1": "msg-a"}))
        monkeypatch.setattr(sys, "stdin", io.StringIO("Body from stdin\nline two\n"))
        gmail = mail_mock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_reply("1", "-", listing=freeze(gmail, ["msg-a"]))

        gmail.reply.assert_called_once_with("msg-a", "Body from stdin\nline two\n")

    def test_unresolvable_number_does_not_reply(self, capsys):
        gmail_commands.INBOX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.INBOX_CACHE.write_text(json.dumps({"1": "msg-a"}))
        gmail = mail_mock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with pytest.raises(typer.Exit):
                handle_gmail_reply("9", "Sounds good")

        gmail.reply.assert_not_called()
        assert "requires --listing" in plain(capsys.readouterr().out)


class TestHandleGmailSendAndSearch:

    def test_send_reports_recipient(self, capsys):
        gmail = mail_mock()

        with patch.dict(os.environ, CONNECTED_ENV, clear=False):
            with patch.object(gmail_commands, "_gmail", return_value=gmail):
                handle_gmail_send("bob@example.com", "Hi", "hello")

        gmail.send.assert_called_once_with("bob@example.com", "Hi", "hello",
                                           cc=None, bcc=None, attachments=None)
        output = plain(capsys.readouterr().out)
        assert "bob@example.com" in output
        assert "Sent" in output

    def test_send_passes_cc_and_bcc(self):
        gmail = mail_mock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_send("bob@example.com", "Hi", "hello",
                              cc="carol@example.com", bcc="dan@example.com")

        assert gmail.send.call_args.kwargs == {"cc": "carol@example.com",
                                               "bcc": "dan@example.com",
                                               "attachments": None}

    def test_send_reads_stdin_body(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "stdin", io.StringIO("piped body"))
        gmail = mail_mock()

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
        gmail = mail_mock()
        gmail.list_search.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_search("invoice", last=5)

        gmail.list_search.assert_called_once_with("invoice", max_results=5)
        assert "no emails matching" in capsys.readouterr().out

    def test_search_empty_result_clears_numbers(self):
        gmail = mail_mock()
        gmail.list_search.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_search("invoice", last=5)

        assert cached_rows(gmail_commands.INBOX_CACHE) == {}

    def test_search_results_share_the_inbox_numbering_contract(self, monkeypatch, capsys):
        """`co gmail read <#>` after a search must open the search hit."""
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=True, width=120))
        gmail = mail_mock()
        gmail.list_search.return_value = sample_emails(2)

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_search("invoice", last=2)

        assert cached_rows(gmail_commands.INBOX_CACHE) == {"1": "msg-1", "2": "msg-2"}
        assert "Subject 1" in capsys.readouterr().out


class TestHandleGmailSent:
    def test_prints_sent_listing(self, capsys):
        gmail = mail_mock()
        gmail.list_search.return_value = sample_emails(1)
        gmail._format_dicts.return_value = '1. From: me@example.com ID: sent-a'
        with patch.object(gmail_commands, '_gmail', return_value=gmail):
            handle_gmail_sent(last=5)
        gmail.list_search.assert_called_once_with('in:sent', max_results=5)
        assert 'me@example.com' in capsys.readouterr().out

    def test_sent_preserves_the_explicit_inbox_listing(self, capsys):
        gmail = mail_mock()
        inbox = freeze(gmail, ['inbox-a'])
        gmail.list_search.return_value = sample_emails(1)
        with patch.object(gmail_commands, '_gmail', return_value=gmail):
            handle_gmail_sent(last=5)
        assert _resolve_email_id(gmail, '1', inbox) == 'inbox-a'
        assert cached_rows(gmail_commands.INBOX_CACHE) == {'1': 'msg-1'}


class TestGmailSendAttachmentChecks:
    """The precheck, which exists so a bad path costs a message rather than a
    traceback after megabytes have been base64-encoded."""

    def test_a_missing_file_is_refused_before_the_api_is_touched(self, capsys):
        gmail = mail_mock()

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
        gmail = mail_mock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_send("bob@example.com", "Hi", "hello", attachments=[str(big)])

        gmail.send.assert_called_once()
        assert "exceed" not in capsys.readouterr().out

    def test_over_gmails_own_limit_is_refused(self, tmp_path, capsys):
        huge = tmp_path / "video.mov"
        huge.write_bytes(b"x" * 26_000_000)
        gmail = mail_mock()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with pytest.raises(typer.Exit):
                handle_gmail_send("bob@example.com", "Hi", "hello", attachments=[str(huge)])

        assert "25MB" in capsys.readouterr().out
        gmail.send.assert_not_called()


def sample_draft(**overrides):
    draft = {
        "id": "draft-1",
        "to": "recipient@example.com",
        "cc": "",
        "bcc": "",
        "subject": "Quarterly report",
        "body": "Exact body\n",
        "attachments": [{
            "name": "report.pdf", "type": "application/pdf", "size": 4,
        }],
        "attachment_size": 4,
    }
    draft.update(overrides)
    return draft


@pytest.fixture
def reviewed_cli(monkeypatch):
    from types import SimpleNamespace
    from connectonion.cli.commands import gmail_draft_review as review_module
    manifest = sample_draft(account='one@example.test', **{'from':'one@example.test'},
        body_sha256='digest', mime_size=100, mime_limit=35_000_000, encoded_size=136,
        attachment_limit=25_000_000, warnings=[])
    review = SimpleNamespace(manifest=manifest, token='a'*64, raw='frozen', thread_id=None)
    monkeypatch.setattr(review_module, 'prepare_review', lambda *args:review)
    monkeypatch.setattr(review_module, 'send_reviewed', lambda client,id,token:client._send_draft(id, raw='frozen', thread_id=None))
    monkeypatch.setattr(gmail_commands, 'console', Console(force_terminal=True, width=120))
    monkeypatch.setattr(sys, 'stdin', MagicMock(isatty=lambda:True))
    return review


class TestGmailDraftCommands:
    """The CLI is a staged workflow and every result prints one next command."""

    def test_list_piped_caches_numbers_and_keeps_preview_tip(self, monkeypatch, capsys):
        monkeypatch.setattr(gmail_commands, "console", Console(force_terminal=False, width=120))
        gmail = mail_mock()
        gmail.list_drafts.return_value = [{
            "id": "draft-1", "to": "r@example.com", "subject": "Report", "attachments": 1,
        }]

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_list(last=5)

        output = plain(capsys.readouterr().out)
        assert "1.\tr@example.com" in output
        assert "draft-1" in output
        assert "co gmail draft preview draft-1" in output
        assert cached_rows(gmail_commands.DRAFT_CACHE) == {"1": "draft-1"}

    def test_empty_list_points_to_create(self, capsys):
        gmail = mail_mock()
        gmail.list_drafts.return_value = []

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_list()

        assert "co gmail draft create" in plain(capsys.readouterr().out)

    def test_empty_list_invalidates_previous_numbers(self):
        gmail_commands.DRAFT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        gmail_commands.DRAFT_CACHE.write_text(json.dumps({"1": "old-draft"}))
        gmail = mail_mock()
        gmail.list_drafts.return_value = []
        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_list()
        with pytest.raises(ListingError, match="--listing"):
            gmail_commands._resolve_draft_id(gmail, "1")

    @pytest.mark.parametrize("interruption", [typer.Abort, KeyboardInterrupt, EOFError])
    def test_interrupted_confirmation_keeps_draft_and_prints_tip(self, interruption, capsys, reviewed_cli):
        gmail = mail_mock()
        gmail.get_draft.return_value = sample_draft()
        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with patch.object(typer, "confirm", side_effect=interruption):
                with pytest.raises(typer.Exit) as exc:
                    gmail_commands.handle_gmail_draft_send("draft-1")
        assert exc.value.exit_code == 1
        gmail._send_draft.assert_not_called()
        assert "co gmail draft review draft-1" in plain(capsys.readouterr().out)

    def test_create_stays_unsent_and_points_to_attach(self, capsys):
        gmail = mail_mock()
        gmail.create_draft.return_value = sample_draft()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_create("r@example.com", "S", "B")

        gmail.create_draft.assert_called_once_with("r@example.com", "S", "B", cc=None, bcc=None)
        gmail._send_draft.assert_not_called()
        assert "co gmail draft attach draft-1 <path>" in plain(capsys.readouterr().out)

    def test_create_reads_body_from_stdin(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("Piped body"))
        gmail = mail_mock()
        gmail.create_draft.return_value = sample_draft()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_create("r@example.com", "S", "-")

        assert gmail.create_draft.call_args.args[2] == "Piped body"

    def test_attach_local_stages_and_points_to_preview(self, capsys):
        gmail = mail_mock()
        gmail.add_draft_attachment.return_value = sample_draft()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_attach("draft-1", "report.pdf")

        gmail.add_draft_attachment.assert_called_once_with("draft-1", "report.pdf")
        gmail._send_draft.assert_not_called()
        assert "co gmail draft preview draft-1" in plain(capsys.readouterr().out)

    def test_attach_drive_file_reads_bytes_without_writing_local_file(self, capsys):
        gmail = mail_mock()
        gmail._add_draft_attachment.return_value = sample_draft()
        drive = MagicMock()
        drive.get_account_email.return_value = 'one@example.test'
        drive._read_file.return_value = {
            "id":"drive-file", "name": "Budget.csv", "type": "text/csv", "data": b"a,b",
        }

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with patch("connectonion.cli.commands.gdrive_commands._gdrive", return_value=drive):
                handle_gmail_draft_attach("draft-1", "drive-file", drive=True)

        drive._read_file.assert_called_once()
        gmail._add_draft_attachment.assert_called_once_with(
            "draft-1", "Budget.csv", "text/csv", b"a,b", source={"source":"drive_attachment", "drive_file_id":"drive-file"}
        )
        assert "co gmail draft preview draft-1" in plain(capsys.readouterr().out)

    def test_attach_drive_link_does_not_download_or_change_sharing(self, capsys):
        gmail = mail_mock()
        gmail._add_managed_draft_link.return_value = sample_draft(attachments=[], attachment_size=0)
        drive = MagicMock()
        drive.get_account_email.return_value = 'one@example.test'
        drive.get_info.return_value = {
            "name": "Budget", "link": "https://drive.google.com/file/d/1/view",
        }

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with patch("connectonion.cli.commands.gdrive_commands._gdrive", return_value=drive):
                handle_gmail_draft_attach("draft-1", "drive-file", drive=True, link=True)

        drive._read_file.assert_not_called()
        gmail._add_managed_draft_link.assert_called_once_with("draft-1", drive.get_info.return_value)
        assert "Drive link added" in plain(capsys.readouterr().out)

    def test_link_without_drive_is_a_fix_it_error(self, capsys):
        with pytest.raises(typer.Exit):
            handle_gmail_draft_attach("draft-1", "report.pdf", link=True)

        output = plain(capsys.readouterr().out)
        assert "--link requires --drive" in output
        assert "co gmail draft attach draft-1" in output

    def test_remove_points_back_to_preview(self, capsys):
        gmail = mail_mock()
        gmail.remove_draft_attachment.return_value = sample_draft(attachments=[], attachment_size=0)

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_remove("draft-1", 1)

        gmail.remove_draft_attachment.assert_called_once_with("draft-1", 1)
        assert "co gmail draft preview draft-1" in plain(capsys.readouterr().out)

    def test_replace_with_local_file_points_back_to_preview(self, capsys):
        gmail = mail_mock()
        gmail.replace_draft_attachment.return_value = sample_draft()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_replace("draft-1", 1, "new.pdf")

        gmail.replace_draft_attachment.assert_called_once_with("draft-1", 1, "new.pdf")
        assert "co gmail draft preview draft-1" in plain(capsys.readouterr().out)

    def test_preview_prints_exact_body_manifest_and_send_tip(self, capsys):
        gmail = mail_mock()
        gmail.get_draft.return_value = sample_draft()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            handle_gmail_draft_preview("draft-1")

        output = plain(capsys.readouterr().out)
        assert "Exact body" in output
        assert "report.pdf (application/pdf, 4 bytes)" in output
        assert "co gmail draft review draft-1" in output

    def test_send_decline_keeps_draft_and_exits_nonzero(self, capsys, reviewed_cli):
        gmail = mail_mock()
        gmail.get_draft.return_value = sample_draft()

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with patch.object(typer, "confirm", return_value=False):
                with pytest.raises(typer.Exit) as exited:
                    handle_gmail_draft_send("draft-1")

        assert exited.value.exit_code == 1
        gmail._send_draft.assert_not_called()
        output = plain(capsys.readouterr().out)
        assert "Not sent" in output
        assert "co gmail draft review draft-1" in output

    def test_send_confirms_after_preview_and_points_to_sent(self, capsys, reviewed_cli):
        gmail = mail_mock()
        gmail.get_draft.return_value = sample_draft()
        gmail._send_draft.return_value = {"id": "message-1"}

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with patch.object(typer, "confirm", return_value=True):
                handle_gmail_draft_send("draft-1")

        output = plain(capsys.readouterr().out)
        assert "Exact body" in output
        gmail._send_draft.assert_called_once_with("draft-1", raw='frozen', thread_id=None)
        assert "co gmail sent" in output

    def test_unknown_cached_number_points_to_list(self, capsys):
        gmail_commands.DRAFT_CACHE.parent.mkdir(parents=True)
        gmail_commands.DRAFT_CACHE.write_text(json.dumps({"1": "draft-1"}))

        with patch.object(gmail_commands, "_gmail", return_value=MagicMock()):
            with pytest.raises(typer.Exit):
                handle_gmail_draft_preview("9")

        assert "co gmail draft list" in plain(capsys.readouterr().out)

    def test_provider_permission_error_is_sanitized(self, capsys):
        from googleapiclient.errors import HttpError

        response = MagicMock(status=403, reason="Forbidden")
        gmail = mail_mock()
        gmail.list_drafts.side_effect = HttpError(
            response, b'{"access_token":"must-not-appear"}'
        )

        with patch.object(gmail_commands, "_gmail", return_value=gmail):
            with pytest.raises(typer.Exit):
                handle_gmail_draft_list()

        output = plain(capsys.readouterr().out)
        assert "must-not-appear" not in output
        assert "co auth google" in output
