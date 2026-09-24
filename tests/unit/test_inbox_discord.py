"""Unit tests for the Discord inbox provider.

LLM-Note: Tests for connectonion.inbox.discord

What it tests:
- A MESSAGE_CREATE becomes a Message; DMs are addressed to us, guild messages only when they mention or reply to us
- Bot, webhook, self-authored and malformed events never reach the inbox
- The Gateway session: Hello → Identify, dispatch, sequence tracking, op 7 reconnect, Resume with the kept state
- A missed heartbeat ACK closes the socket instead of waiting forever
- A close code no reconnect fixes (4004 bad token, 4014 Message Content intent off) ends the listener with ListenerStopped
- send(): the 2000-character boundary before the network, one 429 retry, a nonce that makes a retried reply idempotent, no token in errors
- `co discord` registers the inbox verbs, and edit/delete/react name Discord's own endpoints

Components under test:
- Module: connectonion/inbox/discord.py
- Registration: connectonion/inbox/__init__.py, connectonion/cli/main.py (_inbox_group)

No network: the socket and requests are fakes.
"""

import asyncio
import json

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from connectonion.inbox import ListenerStopped, provider
from connectonion.inbox import discord as discord_module
from connectonion.inbox.discord import Discord, GatewayClosed, Reconnect
from connectonion.inbox.store import Inbox

ME = "999999999999999999"

MESSAGE = {
    "id": "123456789012345678",
    "channel_id": "234567890123456789",
    "guild_id": "345678901234567890",
    "author": {"id": "456789012345678901", "bot": False, "username": "aaron", "global_name": "Aaron"},
    "content": "check the failed deployment",
    "mentions": [{"id": ME}],
    "timestamp": "2026-09-05T05:00:00.000000+00:00",
}


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-secret-token")
    value = Discord()
    value._me_id = ME
    value._me_name = "OpsBot"
    return value


@pytest.fixture
def box(tmp_path):
    return Inbox("discord", home=tmp_path / "discord")


class FakeSocket:
    """A Gateway that plays `payloads` in order, then either ends cleanly or
    raises `then` (a ConnectionClosed, to stand in for a close code)."""

    def __init__(self, payloads, then=None):
        self.payloads = [json.dumps(value) for value in payloads]
        self.then = then
        self.sent = []
        self.closed = None

    async def recv(self):
        return self.payloads.pop(0)

    async def send(self, value):
        self.sent.append(json.loads(value))

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.payloads:
            if self.then is not None:
                raise self.then
            raise StopAsyncIteration
        return self.payloads.pop(0)


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload

    def json(self):
        return self.payload


def hello(interval=60000):
    return {"op": 10, "d": {"heartbeat_interval": interval}}


READY = {"op": 0, "t": "READY", "s": 1, "d": {
    "session_id": "session", "resume_gateway_url": "wss://resume.discord.test",
    "user": {"id": ME, "username": "OpsBot"}}}


def closed(code, reason=""):
    return ConnectionClosedError(Close(code, reason), None)


class TestAnEventBecomesAMessage:
    def test_message_create_normalizes_and_detects_the_current_bot(self, bot):
        record = bot.to_message(MESSAGE).to_dict()

        assert record["id"] == "123456789012345678"
        assert record["chat"] == "234567890123456789"
        assert record["thread"] is None
        assert record["sender"] == "456789012345678901"
        assert record["sender_name"] == "Aaron"
        assert record["text"] == "check the failed deployment"
        assert record["kind"] == "text"
        assert record["mentioned"] is True
        assert record["at"] == "2026-09-05T05:00:00.000000+00:00"

    def test_a_dm_is_addressed_but_an_unmentioned_guild_message_is_not(self, bot):
        dm = {**MESSAGE, "guild_id": None, "mentions": []}
        guild = {**MESSAGE, "mentions": []}

        assert bot.to_message(dm).mentioned is True
        assert bot.to_message(guild).mentioned is False

    def test_a_reply_to_the_bot_is_addressed_and_quoted_as_ours(self, bot):
        reply = {**MESSAGE, "mentions": [], "referenced_message": {
            "id": "111", "author": {"id": ME}, "content": "deploy?"}}

        message = bot.to_message(reply)

        assert message.mentioned is True
        assert message.quoted == {"id": "111", "sender": ME, "text": "deploy?",
                                  "kind": "text", "from_me": True}

    def test_an_attachment_without_text_is_named_by_its_type(self, bot):
        photo = {**MESSAGE, "content": "", "attachments": [{"content_type": "image/png"}]}
        pdf = {**MESSAGE, "content": "", "attachments": [{"content_type": "application/pdf"}]}

        assert (bot.to_message(photo).text, bot.to_message(photo).kind) == ("[image]", "image")
        assert bot.to_message(pdf).kind == "document"

    @pytest.mark.parametrize("change", [
        {"author": {"id": "456", "bot": True}},
        {"webhook_id": "789"},
        {"author": {"id": ME, "bot": False}},
        {"id": ""},
        {"content": ""},  # a sticker or embed: nothing to read, nothing to answer
    ])
    def test_bot_webhook_self_and_empty_events_are_ignored(self, bot, change):
        assert bot.to_message({**MESSAGE, **change}) is None


class TestTheGateway:
    def test_identify_and_resume_carry_the_minimum_state(self, bot):
        identify = bot._authentication_payload()
        assert identify["op"] == 2
        assert identify["d"]["token"] == "discord-secret-token"
        assert identify["d"]["intents"] & (1 << 15), "Message Content intent"

        bot._session_id, bot._sequence = "session", 42
        assert bot._authentication_payload() == {
            "op": 6, "d": {"token": "discord-secret-token", "session_id": "session", "seq": 42}}

    def test_a_session_dispatches_then_reconnects_with_what_resume_needs(self, bot, box):
        socket = FakeSocket([hello(), READY, {"op": 0, "t": "MESSAGE_CREATE", "s": 2, "d": MESSAGE},
                             {"op": 7, "d": None}])

        with pytest.raises(Reconnect):
            asyncio.run(bot._session(socket, box, raw=False))

        assert socket.sent[0]["op"] == 2
        assert bot._sequence == 2
        assert bot._resume_url == "wss://resume.discord.test"
        assert bot._gateway_url() == "wss://resume.discord.test/?v=10&encoding=json"
        assert [p.name.split("-", 1)[1] for p in box.unread()] == [MESSAGE["id"]]
        state = box.connection_state()
        assert (state["state"], state["account"]) == ("connected", "OpsBot")
        # The next connection resumes rather than identifying afresh.
        assert bot._authentication_payload()["op"] == 6

    def test_a_replayed_event_after_resume_is_dropped_by_the_inbox(self, bot, box):
        event = {"op": 0, "t": "MESSAGE_CREATE", "s": 2, "d": MESSAGE}
        asyncio.run(bot._session(FakeSocket([hello(), READY, event]), box, raw=False))
        asyncio.run(bot._session(FakeSocket([hello(), {"op": 0, "t": "RESUMED", "s": 2, "d": {}}, event]),
                                 box, raw=False))

        assert len(box.unread()) == 1
        assert f"duplicate {MESSAGE['id']} dropped" in box.logfile.read_text()

    def test_a_message_that_could_not_be_written_is_not_acknowledged(self, bot, box, monkeypatch):
        """The sequence is what Resume tells Discord we have. It must not move
        past a message that never reached the disk, or the replay skips it."""
        def full_disk(message, raw=False):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(box, "deliver", full_disk)
        socket = FakeSocket([hello(), READY, {"op": 0, "t": "MESSAGE_CREATE", "s": 2, "d": MESSAGE}])

        with pytest.raises(OSError):
            asyncio.run(bot._session(socket, box, raw=False))

        assert bot._sequence == 1

    def test_an_invalid_session_forgets_it_so_the_next_connection_identifies(self, bot, box, monkeypatch):
        async def no_wait(_):
            return None

        monkeypatch.setattr(discord_module.asyncio, "sleep", no_wait)
        socket = FakeSocket([hello(), READY, {"op": 9, "d": False}])

        with pytest.raises(Reconnect):
            asyncio.run(bot._session(socket, box, raw=False))

        assert bot._authentication_payload()["op"] == 2
        assert bot._gateway_url() == discord_module.GATEWAY

    def test_a_close_code_surfaces_as_gateway_closed(self, bot, box):
        socket = FakeSocket([hello()], then=closed(4014, "Disallowed intent(s)."))

        with pytest.raises(GatewayClosed) as raised:
            asyncio.run(bot._session(socket, box, raw=False))

        assert raised.value.code == 4014

    def test_a_missed_heartbeat_ack_closes_the_socket(self, bot):
        socket = FakeSocket([])

        async def beat_twice():
            await bot._heartbeat(socket, 0.001)

        asyncio.run(asyncio.wait_for(beat_twice(), 1))

        assert socket.sent == [{"op": 1, "d": None}]
        assert socket.closed == (4000, "heartbeat not acknowledged")


class TestTheListener:
    def _connect(self, monkeypatch, *sockets):
        """websockets.connect handing out `sockets` in order."""
        import websockets

        queue = list(sockets)
        urls = []

        class Connection:
            def __init__(self, url, **_):
                urls.append(url)
                self.socket = queue.pop(0)

            async def __aenter__(self):
                if isinstance(self.socket, BaseException):
                    raise self.socket
                return self.socket

            async def __aexit__(self, *exc):
                return False

        async def no_wait(_):
            return None

        monkeypatch.setattr(websockets, "connect", Connection)
        monkeypatch.setattr(discord_module.asyncio, "sleep", no_wait)
        return urls

    @pytest.mark.parametrize("code, words", [
        (4004, "rejected the bot token"),
        (4014, "Message Content intent is not enabled"),
    ])
    def test_a_close_no_reconnect_fixes_stops_the_listener(self, bot, box, monkeypatch, code, words):
        self._connect(monkeypatch, FakeSocket([hello()], then=closed(code)))

        with pytest.raises(ListenerStopped) as stopped:
            bot.run(box)

        assert words in str(stopped.value) and "Next:" in str(stopped.value)
        assert box.connection_state()["state"] == "stopped"

    def test_a_dropped_connection_reconnects_and_resumes_where_it_was(self, bot, box, monkeypatch):
        first = FakeSocket([hello(), READY, {"op": 0, "t": "MESSAGE_CREATE", "s": 2, "d": MESSAGE}],
                           then=ConnectionClosedError(None, None))  # the network went away
        second = FakeSocket([hello()], then=closed(4004))
        urls = self._connect(monkeypatch, first, OSError("network is unreachable"), second)

        with pytest.raises(ListenerStopped):
            bot.run(box)

        assert urls[0] == discord_module.GATEWAY
        assert urls[1:] == ["wss://resume.discord.test/?v=10&encoding=json"] * 2
        assert second.sent[0] == {"op": 6, "d": {"token": "discord-secret-token",
                                                 "session_id": "session", "seq": 2}}
        log = box.logfile.read_text()
        assert "gateway closed (no close frame)" in log and "gateway OSError" in log
        assert "discord-secret-token" not in log


class TestSending:
    def test_a_reply_references_the_message_pings_nobody_and_retries_one_rate_limit(self, bot, monkeypatch):
        responses = [Response(429, {"retry_after": 0}), Response(200, {"id": "sent-id"})]
        posted = []
        monkeypatch.setattr(discord_module.requests, "post",
                            lambda url, **kwargs: posted.append((url, kwargs)) or responses.pop(0))
        monkeypatch.setattr(discord_module.time, "sleep", lambda _: None)

        assert bot.send("234", "hello", reply_to="123") == "sent-id"

        assert len(posted) == 2
        url, kwargs = posted[0]
        assert url == "https://discord.com/api/v10/channels/234/messages"
        body = kwargs["json"]
        assert body["message_reference"] == {"message_id": "123", "channel_id": "234",
                                             "fail_if_not_exists": False}
        assert body["allowed_mentions"] == {"parse": [], "replied_user": False}
        assert kwargs["headers"]["Authorization"] == "Bot discord-secret-token"

    def test_the_same_reply_twice_carries_the_same_nonce_and_again_does_not(self, bot, monkeypatch):
        bodies = []
        monkeypatch.setattr(discord_module.requests, "post",
                            lambda url, **kwargs: bodies.append(kwargs["json"]) or Response(200, {"id": "x"}))

        bot.send("234", "hello", reply_to="123")
        bot.send("234", "hello", reply_to="123")
        bot.send("234", "hello", reply_to="123", fresh=True)

        nonces = [b["nonce"] for b in bodies]
        assert nonces[0] == nonces[1] != nonces[2]
        assert all(len(n) <= 25 and b["enforce_nonce"] for n, b in zip(nonces, bodies))

    def test_overlong_content_is_refused_without_the_network(self, bot, monkeypatch):
        monkeypatch.setattr(discord_module.requests, "post",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")))
        with pytest.raises(RuntimeError, match="2000"):
            bot.send("234", "x" * 2001)

    def test_a_refusal_keeps_discords_words_minus_the_token(self, bot, monkeypatch):
        monkeypatch.setattr(discord_module.requests, "post", lambda url, **kwargs: Response(
            403, {"message": "Missing Access for discord-secret-token"}))

        with pytest.raises(RuntimeError, match=r"Missing Access for \[redacted\]"):
            bot.send("234", "hi")


class TestSetup:
    def test_missing_token_names_the_portal_and_the_intent(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        (problem,) = Discord().missing()
        assert "DISCORD_BOT_TOKEN" in problem and "Message Content" in problem

    def test_check_reports_a_bad_token_in_discords_words(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "bad")
        monkeypatch.setattr(discord_module.requests, "get", lambda url, **kwargs: Response(
            401, {"message": "401: Unauthorized"}))
        (problem,) = Discord().check()
        assert "Unauthorized" in problem and "Next:" in problem

    def test_it_is_a_registered_provider(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "t")
        assert isinstance(provider("discord"), Discord)

    def test_status_lists_the_token_without_showing_it(self, tmp_path):
        from connectonion.cli.commands.status_commands import _credential_rows

        (tmp_path / "home" / ".co").mkdir(parents=True)
        (tmp_path / "project").mkdir()
        (tmp_path / "home" / ".co" / "keys.env").write_text("DISCORD_BOT_TOKEN=secret-value\n")

        rows = _credential_rows(project_dir=tmp_path / "project", home=tmp_path / "home", environ={})
        row = next(item for item in rows if item["credential"] == "DISCORD_BOT_TOKEN")

        assert row["provider"] == "Discord"
        assert "secret-value" not in repr(rows)


class TestTheCommandGroup:
    def test_co_discord_has_the_inbox_verbs(self):
        import typer.main

        from connectonion.cli.main import app

        group = typer.main.get_command(app).commands["discord"]
        assert {"listen", "receive", "send", "reply", "done", "check", "ls", "chats", "log",
                "consume"} <= set(group.commands)

    def test_edit_names_discords_endpoint_not_feishus(self, bot, monkeypatch, capsys):
        from connectonion.cli.commands import listen_commands

        monkeypatch.setattr(listen_commands, "provider", lambda name: bot)

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_edit("discord", MESSAGE["id"], "x")

        assert exit_.value.code == 1
        err = capsys.readouterr().err
        assert "PATCH /channels" in err and "/im/v1" not in err
