"""Four Outlook complaints from one working day, each pinned to the command a user typed.

#1312 — a valid, unexpired token was thrown away and every command died with the
        refresh broker. The stored token must serve `co outlook inbox` with no
        OpenOnion key and no backend call at all.
#1313 — a dead OpenOnion key was reported as "Microsoft session expired", and a
        missing key as "Microsoft Mail permission missing". Three causes, three
        different next commands: `co auth`, `co auth microsoft`, and re-consent.
#1314 — `send --at` never said how to cancel. Every scheduled send and reply now
        ends by naming `co outlook scheduled`, and the help groups the three
        scheduling commands as one feature.
#1247 — `reply` had no --cc / --bcc, so adding a third person meant starting a
        new thread. The flags ride on Graph's reply action and on the deferred
        reply draft, so the conversation stays threaded.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner
from rich.text import Text

from connectonion.cli.main import app
from connectonion.cli.commands import outlook_commands

VALID = {
    "MICROSOFT_ACCESS_TOKEN": "stored-token",
    "MICROSOFT_REFRESH_TOKEN": "stored-refresh",
    "MICROSOFT_SCOPES": "Mail.ReadWrite,Mail.Send",
    "MICROSOFT_EMAIL": "me@example.com",
    "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z",
}


def plain(output: str) -> str:
    return Text.from_ansi(output).plain


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """No real ~/.co, no ambient OpenOnion key unless a test sets one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(home / ".co"))
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)
    monkeypatch.setattr(outlook_commands, "INBOX_CACHE", home / "outlook_last_inbox.json")
    return home


class TestAValidTokenNeedsNoBroker:
    """#1312: the mailbox is reachable, so the CLI must reach it."""

    def test_inbox_uses_the_stored_token_without_any_backend_call(self, isolated_home, monkeypatch):
        graph = MagicMock(status_code=200, text='{"value": []}')
        graph.json.return_value = {"value": []}
        calls = []

        def request(method, url, headers=None, **kwargs):
            calls.append((method, url, headers["Authorization"]))
            return graph

        monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", request)
        monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.post",
                            lambda *a, **k: pytest.fail("refresh broker was called"))
        with patch.dict(os.environ, VALID, clear=False):
            result = CliRunner().invoke(app, ["outlook", "inbox"])

        assert result.exit_code == 0, result.output
        assert calls and all(auth == "Bearer stored-token" for _, _, auth in calls)
        assert calls[0][1].startswith("https://graph.microsoft.com/v1.0/")


class TestTheErrorNamesTheLayerThatFailed:
    """#1313: each failure points at the credential that is actually broken."""

    def _expiring(self):
        return {**VALID, "MICROSOFT_TOKEN_EXPIRES_AT":
                (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()}

    def test_missing_openonion_key_is_not_a_missing_microsoft_scope(self, isolated_home):
        with patch.dict(os.environ, self._expiring(), clear=False):
            result = CliRunner().invoke(app, ["outlook", "inbox"])

        output = plain(result.output)
        assert result.exit_code == 1
        assert "permission missing" not in output
        assert re.search(r"^Next: co auth$", output, re.MULTILINE), output

    def test_dead_openonion_key_is_not_a_microsoft_expiry(self, isolated_home, monkeypatch):
        rejected = MagicMock(status_code=401)
        rejected.json.return_value = {"detail": "Invalid token"}
        monkeypatch.setenv("OPENONION_API_KEY", "dead-key")
        monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.post", lambda *a, **k: rejected)
        with patch.dict(os.environ, self._expiring(), clear=False):
            result = CliRunner().invoke(app, ["outlook", "inbox"])

        output = plain(result.output)
        assert result.exit_code == 1
        assert "Microsoft session expired" not in output and "Microsoft authorization expired" not in output
        assert re.search(r"^Next: co auth$", output, re.MULTILINE), output

    def test_microsoft_revocation_points_to_microsoft(self, isolated_home, monkeypatch):
        revoked = MagicMock(status_code=401)
        revoked.json.return_value = {"detail": {"error": "reauth_required"}}
        monkeypatch.setenv("OPENONION_API_KEY", "good-key")
        monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.post", lambda *a, **k: revoked)
        with patch.dict(os.environ, self._expiring(), clear=False):
            result = CliRunner().invoke(app, ["outlook", "inbox"])

        assert result.exit_code == 1
        assert re.search(r"^Next: co auth microsoft$", plain(result.output), re.MULTILINE)

    def test_expiring_token_with_no_refresh_token_is_an_incomplete_record(self, isolated_home):
        """Not 'invalid input; check the command arguments' — nothing about the
        arguments is wrong, the saved record is missing its refresh half."""
        record = {**self._expiring(), "MICROSOFT_REFRESH_TOKEN": ""}
        with patch.dict(os.environ, record, clear=False):
            result = CliRunner().invoke(app, ["outlook", "inbox"])

        output = plain(result.output)
        assert result.exit_code == 1
        assert "check the command arguments" not in output
        assert re.search(r"^Next: co auth microsoft$", output, re.MULTILINE), output

    def test_mark_read_reads_the_scope_from_the_record_not_the_process(self, isolated_home, monkeypatch):
        """The write-scope check must follow the same record as everything else."""
        outlook = MagicMock()
        outlook._credentials.scopes = {"Mail.ReadWrite", "Mail.Send"}
        outlook.get_email_body.return_value = "From: a@b.c\n--- Email Body ---\nhi"
        monkeypatch.delenv("MICROSOFT_SCOPES", raising=False)
        with patch.object(outlook_commands, "_outlook", return_value=outlook):
            outlook_commands.handle_outlook_read("msg-1", mark_read=True)
        outlook.mark_read.assert_called_once_with("msg-1")


class TestSchedulingIsOneDiscoverableFeature:
    """#1314: the send that most needs taking back is the one that says how."""

    @pytest.fixture
    def outlook(self, isolated_home):
        client = MagicMock()
        client._credentials.get.return_value = "me@example.com"
        with patch.dict(os.environ, VALID, clear=False), \
             patch.object(outlook_commands, "_outlook", return_value=client):
            yield client

    def test_scheduled_send_names_the_cancel_path(self, outlook):
        result = CliRunner().invoke(app, ["outlook", "send", "x@y.com", "Hi", "Body", "--at", "+2h"])
        assert result.exit_code == 0, result.output
        assert plain(result.output).strip().splitlines()[-1] == "Next: co outlook scheduled"
        assert "co outlook cancel <#>" in plain(result.output)

    def test_scheduled_reply_names_the_cancel_path(self, outlook):
        result = CliRunner().invoke(app, ["outlook", "reply", "AAMkAGI2", "On it", "--at", "+30m"])
        assert result.exit_code == 0, result.output
        assert plain(result.output).strip().splitlines()[-1] == "Next: co outlook scheduled"

    def test_immediate_send_still_ends_with_a_next_command(self, outlook):
        result = CliRunner().invoke(app, ["outlook", "send", "x@y.com", "Hi", "Body"])
        assert result.exit_code == 0, result.output
        assert plain(result.output).strip().splitlines()[-1] == "Next: co outlook sent"

    def test_send_help_says_how_to_cancel(self):
        output = plain(CliRunner().invoke(app, ["outlook", "send", "--help"]).output)
        assert "co outlook cancel" in output

    def test_group_help_shows_scheduling_as_one_feature(self):
        output = plain(CliRunner().invoke(app, ["outlook", "--help"]).output)
        assert "Scheduled sends" in output
        block = output.split("Scheduled sends", 1)[1]
        assert "scheduled" in block and "cancel" in block


class TestReplyCarriesCcAndBcc:
    """#1247: a threaded reply can copy a third person."""

    def _replied(self, mock_request, **kwargs):
        from connectonion.useful_tools.outlook import Outlook
        with patch.dict(os.environ, VALID, clear=False):
            return Outlook().reply("msg-1", "Thanks", **kwargs)

    def test_immediate_reply_sets_recipients_on_the_reply_action(self, monkeypatch):
        calls = []
        ok = MagicMock(status_code=202, text="")

        def request(method, url, **kwargs):
            calls.append((method, url, kwargs.get("json")))
            return ok

        monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", request)
        self._replied(request, cc="a@x.com, b@x.com", bcc="c@x.com")

        (method, url, body), = calls
        assert method == "POST" and url.endswith("/me/messages/msg-1/reply")
        assert body["comment"] == "<p>Thanks</p>"
        assert body["message"]["ccRecipients"] == [
            {"emailAddress": {"address": "a@x.com"}}, {"emailAddress": {"address": "b@x.com"}}]
        assert body["message"]["bccRecipients"] == [{"emailAddress": {"address": "c@x.com"}}]

    def test_scheduled_reply_patches_recipients_onto_the_deferred_draft(self, monkeypatch):
        calls = []
        created = MagicMock(status_code=201, text='{"id": "draft-9"}')
        created.json.return_value = {"id": "draft-9"}
        ok = MagicMock(status_code=200, text="")

        def request(method, url, **kwargs):
            calls.append((method, url, kwargs.get("json")))
            return created if url.endswith("/createReply") else ok

        monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", request)
        self._replied(request, send_at="2026-07-06T15:30:00Z", cc="a@x.com")

        patched = [body for method, url, body in calls if method == "PATCH"]
        assert len(patched) == 1
        assert patched[0]["ccRecipients"] == [{"emailAddress": {"address": "a@x.com"}}]
        assert "bccRecipients" not in patched[0]
        assert patched[0]["singleValueExtendedProperties"][0]["value"] == "2026-07-06T15:30:00Z"

    def test_reply_without_cc_is_unchanged(self, monkeypatch):
        calls = []
        ok = MagicMock(status_code=202, text="")
        monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request",
                            lambda m, u, **k: calls.append(k.get("json")) or ok)
        self._replied(None)
        assert calls == [{"comment": "<p>Thanks</p>"}]

    def test_cli_forwards_the_flags_and_prints_them(self, isolated_home):
        client = MagicMock()
        client._credentials.get.return_value = "me@example.com"
        with patch.dict(os.environ, VALID, clear=False), \
             patch.object(outlook_commands, "_outlook", return_value=client):
            result = CliRunner().invoke(app, ["outlook", "reply", "AAMkAGI2", "Thanks",
                                              "--cc", "a@x.com", "--bcc", "c@x.com"])
        assert result.exit_code == 0, result.output
        assert client.reply.call_args.kwargs["cc"] == "a@x.com"
        assert client.reply.call_args.kwargs["bcc"] == "c@x.com"
        assert "Cc: a@x.com" in plain(result.output)
