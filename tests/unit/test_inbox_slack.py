"""Unit tests for the Slack inbox provider.

LLM-Note: Tests for connectonion.inbox.slack

What it tests:
- A message.im / app_mention / message.channels event becomes a Message with id "<channel>:<ts>";
  DMs and @mentions are addressed to us, and so is a thread the bot started or replied in
- Bot messages (including our own), edits, deletions, joins and malformed events never reach the inbox
- The Socket Mode session: hello → connected, events_api written THEN acknowledged by envelope id,
  an event that could not be written is not acknowledged, disconnect → reconnect, link_disabled → stop
- The listener: a fresh URL from apps.connections.open for every connection, reconnect after a drop,
  a token Slack rejects ends it with ListenerStopped, tokens never in the log
- send(): thread_ts on a reply (the thread's root, never a reply's ts), the 40,000-character
  boundary before the network, one 429 honoured via Retry-After, no token in errors
- check()/missing(): each missing or misplaced token named with the setup step
- `co slack` registers the inbox verbs, says Experimental, and edit names Slack's own endpoint

Components under test:
- Module: connectonion/inbox/slack.py
- Registration: connectonion/inbox/__init__.py, connectonion/cli/main.py (_inbox_group)

No network: the socket and requests are fakes.
"""

import asyncio
import json
import re

import pytest
from websockets.exceptions import ConnectionClosedError

from connectonion.inbox import ListenerStopped, provider
from connectonion.inbox import slack as slack_module
from connectonion.inbox.slack import Reconnect, Slack, SlackStopped
from connectonion.inbox.store import Inbox, Message

ME = "U0BOT00000"
APP_TOKEN = "xapp-1-A0-secret-app-token"
BOT_TOKEN = "xoxb-secret-bot-token"

DM = {
    "type": "message", "channel": "D0123456789", "channel_type": "im", "user": "U0AARON000",
    "text": "check the failed deployment", "ts": "1727500000.123456", "event_ts": "1727500000.123456",
}
MENTION = {
    "type": "app_mention", "channel": "C0123456789", "user": "U0AARON000",
    "text": f"<@{ME}> deploy status?", "ts": "1727500100.000200", "event_ts": "1727500100.000200",
}
CHANNEL = {
    "type": "message", "channel": "C0123456789", "channel_type": "channel", "user": "U0AARON000",
    "text": "lunch?", "ts": "1727500200.000300",
}


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("SLACK_APP_TOKEN", APP_TOKEN)
    monkeypatch.setenv("SLACK_BOT_TOKEN", BOT_TOKEN)
    value = Slack()
    value._me_id = ME
    value._me_name = "opsbot"
    return value


@pytest.fixture
def box(tmp_path):
    return Inbox("slack", home=tmp_path / "slack")


class FakeSocket:
    """A Socket Mode connection that plays `frames` in order, then either
    ends cleanly or raises `then` (a ConnectionClosed, for a dropped link)."""

    def __init__(self, frames, then=None):
        self.frames = [json.dumps(value) for value in frames]
        self.then = then
        self.sent = []

    async def send(self, value):
        self.sent.append(json.loads(value))

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.frames:
            if self.then is not None:
                raise self.then
            raise StopAsyncIteration
        return self.frames.pop(0)


class Response:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self.payload = payload
        self.headers = headers or {}

    def json(self):
        return self.payload


HELLO = {"type": "hello", "num_connections": 1, "connection_info": {"app_id": "A0APP"},
         "debug_info": {"approximate_connection_time": 18060}}


def envelope(event, envelope_id="env-1"):
    return {"type": "events_api", "envelope_id": envelope_id, "accepts_response_payload": False,
            "payload": {"type": "event_callback", "event_id": "Ev1", "event": event}}


def queued_ids(box):
    # A set: two files written in the same millisecond sort by name, not arrival.
    return {Message.from_dict(json.loads(p.read_text())).id for p in box.unread()}


class TestAnEventBecomesAMessage:
    def test_a_dm_normalizes_with_channel_and_ts_as_the_id(self, bot):
        record = bot.to_message(DM).to_dict()

        assert record["id"] == "D0123456789:1727500000.123456"
        assert record["chat"] == "D0123456789"
        assert record["thread"] is None
        assert record["sender"] == "U0AARON000"
        assert record["text"] == "check the failed deployment"
        assert record["kind"] == "text"
        assert record["mentioned"] is True
        assert record["at"] == "2024-09-28T05:06:40Z"

    def test_an_app_mention_is_addressed_and_a_plain_channel_message_is_not(self, bot):
        assert bot.to_message(MENTION).mentioned is True
        assert bot.to_message(CHANNEL).mentioned is False
        assert bot.to_message({**CHANNEL, "text": f"hey <@{ME}>"}).mentioned is True

    def test_a_thread_the_bot_started_or_replied_in_is_addressed(self, bot):
        started = {**CHANNEL, "thread_ts": "1727499000.000100", "parent_user_id": ME}
        elsewhere = {**CHANNEL, "thread_ts": "1727499000.000999", "parent_user_id": "U0OTHER000"}

        assert bot.to_message(started).mentioned is True
        assert bot.to_message(started).thread == "1727499000.000100"
        assert bot.to_message(elsewhere).mentioned is False

        bot._threads.add(("C0123456789", "1727499000.000999"))
        assert bot.to_message(elsewhere).mentioned is True

    def test_a_shared_file_without_text_is_named_by_its_type(self, bot):
        photo = {**DM, "subtype": "file_share", "text": "", "files": [{"mimetype": "image/png"}]}
        pdf = {**DM, "subtype": "file_share", "text": "", "files": [{"mimetype": "application/pdf"}]}

        assert (bot.to_message(photo).text, bot.to_message(photo).kind) == ("[image]", "image")
        assert bot.to_message(pdf).kind == "document"

    def test_the_profile_name_is_used_when_slack_sends_one(self, bot):
        named = {**DM, "user_profile": {"real_name": "Aaron Yu", "display_name": "aaron"}}
        assert bot.to_message(named).sender_name == "aaron"

    @pytest.mark.parametrize("change", [
        {"bot_id": "B0SOMEBOT"},
        {"user": ME},
        {"subtype": "bot_message"},
        {"subtype": "message_changed"},
        {"subtype": "message_deleted"},
        {"subtype": "channel_join"},
        {"ts": ""},
        {"channel": ""},
        {"text": ""},
    ])
    def test_bot_self_edit_system_and_empty_events_are_ignored(self, bot, change):
        assert bot.to_message({**DM, **change}) is None


class TestTheSocket:
    def test_an_event_is_written_then_acknowledged_by_its_envelope(self, bot, box):
        socket = FakeSocket([HELLO, envelope(DM, "env-1"), envelope(MENTION, "env-2")])

        asyncio.run(bot._session(socket, box, raw=False))

        assert socket.sent == [{"envelope_id": "env-1"}, {"envelope_id": "env-2"}]
        assert queued_ids(box) == {"D0123456789:1727500000.123456", "C0123456789:1727500100.000200"}
        state = box.connection_state()
        assert (state["state"], state["account"]) == ("connected", "opsbot")

    def test_an_event_that_could_not_be_written_is_not_acknowledged(self, bot, box, monkeypatch):
        """The ACK tells Slack we have it. Sent before the write, a full disk
        would lose the message; withheld, Slack delivers it again."""
        def full_disk(message, raw=False):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(box, "deliver", full_disk)
        socket = FakeSocket([HELLO, envelope(DM)])

        with pytest.raises(OSError):
            asyncio.run(bot._session(socket, box, raw=False))

        assert socket.sent == []

    def test_a_mention_delivered_as_two_events_is_queued_once(self, bot, box):
        both = {**MENTION, "type": "message", "channel_type": "channel"}
        socket = FakeSocket([HELLO, envelope(MENTION, "a"), envelope(both, "b")])

        asyncio.run(bot._session(socket, box, raw=False))

        assert len(box.unread()) == 1
        assert socket.sent == [{"envelope_id": "a"}, {"envelope_id": "b"}]
        assert "duplicate C0123456789:1727500100.000200 dropped" in box.logfile.read_text()

    def test_our_own_reply_in_a_thread_makes_the_thread_ours(self, bot, box):
        ours = {**CHANNEL, "user": ME, "bot_id": "B0OURS", "ts": "1727500300.000400",
                "thread_ts": "1727499000.000999"}
        follow_up = {**CHANNEL, "ts": "1727500400.000500", "thread_ts": "1727499000.000999"}
        socket = FakeSocket([HELLO, envelope(ours, "a"), envelope(follow_up, "b")])

        asyncio.run(bot._session(socket, box, raw=False))

        (record,) = box.history()
        assert record["id"] == "C0123456789:1727500400.000500" and record["mentioned"] is True

    def test_other_envelopes_are_acknowledged_and_ignored(self, bot, box):
        socket = FakeSocket([HELLO, {"type": "slash_commands", "envelope_id": "s-1", "payload": {}},
                             envelope({"type": "reaction_added", "user": "U1"}, "r-1")])

        asyncio.run(bot._session(socket, box, raw=False))

        assert socket.sent == [{"envelope_id": "s-1"}, {"envelope_id": "r-1"}]
        assert box.unread() == []

    @pytest.mark.parametrize("reason", ["refresh_requested", "warning", "too_many_websockets"])
    def test_a_disconnect_asks_for_a_new_connection(self, bot, box, reason):
        socket = FakeSocket([HELLO, {"type": "disconnect", "reason": reason}])

        with pytest.raises(Reconnect):
            asyncio.run(bot._session(socket, box, raw=False))

    def test_socket_mode_switched_off_stops_for_good(self, bot, box):
        socket = FakeSocket([HELLO, {"type": "disconnect", "reason": "link_disabled"}])

        with pytest.raises(SlackStopped) as stopped:
            asyncio.run(bot._session(socket, box, raw=False))

        assert stopped.value.reason == "link_disabled"


class TestTheListener:
    def _wire(self, monkeypatch, sockets, opened=None, auth=None):
        """websockets.connect handing out `sockets` in order, and requests.post
        answering auth.test and apps.connections.open."""
        import websockets

        queue = list(sockets)
        urls = []
        opened = list(opened or [])
        calls = []

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

        def post(url, **kwargs):
            calls.append((url, kwargs))
            if url.endswith("auth.test"):
                return auth or Response(200, {"ok": True, "user_id": ME, "user": "opsbot"})
            if opened:
                return opened.pop(0)
            return Response(200, {"ok": True, "url": f"wss://wss.slack.test/link/?ticket={len(urls)}"})

        async def no_wait(_):
            return None

        monkeypatch.setattr(websockets, "connect", Connection)
        monkeypatch.setattr(slack_module.requests, "post", post)
        monkeypatch.setattr(slack_module.asyncio, "sleep", no_wait)
        return urls, calls

    def test_every_connection_gets_a_fresh_url_and_a_drop_reconnects(self, bot, box, monkeypatch):
        first = FakeSocket([HELLO, envelope(DM)], then=ConnectionClosedError(None, None))
        second = FakeSocket([HELLO, {"type": "disconnect", "reason": "link_disabled"}])
        urls, calls = self._wire(monkeypatch, [first, OSError("network is unreachable"), second])

        with pytest.raises(ListenerStopped) as stopped:
            bot.run(box)

        assert urls == [f"wss://wss.slack.test/link/?ticket={n}" for n in range(3)]
        opens = [kwargs for url, kwargs in calls if url.endswith("apps.connections.open")]
        assert len(opens) == 3
        assert opens[0]["headers"]["Authorization"] == f"Bearer {APP_TOKEN}"
        assert "Socket Mode" in str(stopped.value) and "Next:" in str(stopped.value)
        assert len(box.unread()) == 1
        log = box.logfile.read_text()
        assert "socket closed" in log and "OSError" in log
        assert APP_TOKEN not in log and BOT_TOKEN not in log
        assert box.connection_state()["state"] == "stopped"

    @pytest.mark.parametrize("error, words", [
        ("invalid_auth", "rejected"),
        ("not_allowed_token_type", "xapp-"),
        ("token_revoked", "rejected"),
    ])
    def test_an_app_token_slack_rejects_stops_the_listener(self, bot, box, monkeypatch, error, words):
        self._wire(monkeypatch, [], opened=[Response(200, {"ok": False, "error": error})])

        with pytest.raises(ListenerStopped) as stopped:
            bot.run(box)

        assert words in str(stopped.value) and "Next:" in str(stopped.value)
        assert APP_TOKEN not in str(stopped.value)

    def test_a_bot_token_slack_rejects_stops_before_connecting(self, bot, box, monkeypatch):
        urls, _ = self._wire(monkeypatch, [], auth=Response(200, {"ok": False, "error": "invalid_auth"}))

        with pytest.raises(ListenerStopped) as stopped:
            bot.run(box)

        assert "SLACK_BOT_TOKEN" in str(stopped.value) and urls == []

    def test_threads_the_bot_replied_in_survive_a_restart(self, bot, box, monkeypatch):
        parent = {**CHANNEL, "text": f"<@{ME}> look", "ts": "1727499000.000999"}
        box.deliver(bot.to_message(parent))
        box.record_sent(chat="C0123456789", text="on it", reply_to="C0123456789:1727499000.000999",
                        provider_id="C0123456789:1727499100.000001")
        follow_up = {**CHANNEL, "ts": "1727500400.000500", "thread_ts": "1727499000.000999"}
        socket = FakeSocket([HELLO, envelope(follow_up),
                             {"type": "disconnect", "reason": "link_disabled"}])
        self._wire(monkeypatch, [socket])

        with pytest.raises(ListenerStopped):
            Slack().run(box)

        assert box.history()[-1]["mentioned"] is True


class TestSending:
    def _post(self, monkeypatch, *responses):
        responses = list(responses)
        posted = []
        monkeypatch.setattr(slack_module.requests, "post",
                            lambda url, **kwargs: posted.append((url, kwargs)) or responses.pop(0))
        monkeypatch.setattr(slack_module.time, "sleep", lambda _: None)
        return posted

    def test_a_reply_goes_into_the_messages_thread_and_retries_one_rate_limit(self, bot, monkeypatch):
        posted = self._post(monkeypatch,
                            Response(429, {"ok": False, "error": "ratelimited"}, {"Retry-After": "1"}),
                            Response(200, {"ok": True, "channel": "C0123456789", "ts": "1727500500.000600"}))

        sent = bot.send("C0123456789", "hello", reply_to="C0123456789:1727500100.000200")

        assert sent == "C0123456789:1727500500.000600"
        assert len(posted) == 2
        url, kwargs = posted[0]
        assert url == "https://slack.com/api/chat.postMessage"
        assert kwargs["json"] == {"channel": "C0123456789", "text": "hello",
                                  "thread_ts": "1727500100.000200"}
        assert kwargs["headers"]["Authorization"] == f"Bearer {BOT_TOKEN}"

    def test_a_reply_to_a_reply_goes_to_the_threads_root(self, bot, box, monkeypatch):
        """Slack: "Avoid using a reply's ts value; use its parent instead." """
        monkeypatch.setenv("CO_INBOX_HOME", str(box.root.parent))
        in_thread = {**CHANNEL, "ts": "1727500400.000500", "thread_ts": "1727499000.000999"}
        box.deliver(bot.to_message(in_thread))
        posted = self._post(monkeypatch, Response(200, {"ok": True, "channel": "C0123456789", "ts": "1.2"}))

        bot.send("C0123456789", "hi", reply_to="C0123456789:1727500400.000500")

        assert posted[0][1]["json"]["thread_ts"] == "1727499000.000999"

    def test_a_plain_send_has_no_thread(self, bot, monkeypatch):
        posted = self._post(monkeypatch, Response(200, {"ok": True, "channel": "C1", "ts": "1.2"}))

        assert bot.send("C1", "hi") == "C1:1.2"
        assert "thread_ts" not in posted[0][1]["json"]

    def test_overlong_text_is_refused_without_the_network(self, bot, monkeypatch):
        monkeypatch.setattr(slack_module.requests, "post",
                            lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")))
        with pytest.raises(RuntimeError, match="40000") as refused:
            bot.send("C1", "x" * 40001)
        assert re.search(r"Next: .*co slack", str(refused.value))

    def test_a_refusal_keeps_slacks_words_minus_the_token(self, bot, monkeypatch):
        self._post(monkeypatch, Response(200, {"ok": False, "error": f"not_in_channel {BOT_TOKEN}"}))

        with pytest.raises(RuntimeError) as refused:
            bot.send("C1", "hi")

        assert "not_in_channel" in str(refused.value) and "/invite" in str(refused.value)
        assert BOT_TOKEN not in str(refused.value)

    def test_a_second_rate_limit_is_reported(self, bot, monkeypatch):
        self._post(monkeypatch, Response(429, {"ok": False, "error": "ratelimited"}, {"Retry-After": "1"}),
                   Response(429, {"ok": False, "error": "ratelimited"}, {"Retry-After": "1"}))
        with pytest.raises(RuntimeError, match="ratelimited"):
            bot.send("C1", "hi")


class TestSetup:
    def test_missing_tokens_are_each_named_with_the_setup_step(self, monkeypatch):
        monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        app, bot = Slack().missing()
        assert "SLACK_APP_TOKEN" in app and "Socket Mode" in app and "connections:write" in app
        assert "SLACK_BOT_TOKEN" in bot and "chat:write" in bot and "Install" in bot

    def test_tokens_in_each_others_places_are_caught_before_the_network(self, monkeypatch):
        monkeypatch.setenv("SLACK_APP_TOKEN", "xoxb-wrong")
        monkeypatch.setenv("SLACK_BOT_TOKEN", "xapp-wrong")
        problems = Slack().missing()
        assert len(problems) == 2 and all("xapp-" in p and "xoxb-" in p for p in problems)
        assert not any("wrong" in p for p in problems)

    def test_check_reports_a_rejected_token_in_slacks_words(self, monkeypatch):
        monkeypatch.setenv("SLACK_APP_TOKEN", APP_TOKEN)
        monkeypatch.setenv("SLACK_BOT_TOKEN", BOT_TOKEN)
        monkeypatch.setattr(slack_module.requests, "post", lambda url, **kwargs: Response(
            200, {"ok": False, "error": "invalid_auth"}))
        problems = Slack().check()
        assert problems and all("invalid_auth" in p and "Next:" in p for p in problems)

    def test_check_passes_when_both_tokens_work(self, bot, monkeypatch):
        monkeypatch.setattr(slack_module.requests, "post", lambda url, **kwargs: Response(
            200, {"ok": True, "user_id": ME, "user": "opsbot", "url": "wss://x"}))
        assert bot.check() == []

    def test_it_is_a_registered_provider(self, bot):
        assert isinstance(provider("slack"), Slack)

    def test_status_lists_both_tokens_without_showing_them(self, tmp_path):
        from connectonion.cli.commands.status_commands import _credential_rows

        (tmp_path / "home" / ".co").mkdir(parents=True)
        (tmp_path / "project").mkdir()
        (tmp_path / "home" / ".co" / "keys.env").write_text(
            "SLACK_APP_TOKEN=xapp-secret-value\nSLACK_BOT_TOKEN=xoxb-secret-value\n")

        rows = _credential_rows(project_dir=tmp_path / "project", home=tmp_path / "home", environ={})
        names = {item["credential"]: item["provider"] for item in rows}

        assert names["SLACK_APP_TOKEN"] == names["SLACK_BOT_TOKEN"] == "Slack"
        assert "secret-value" not in repr(rows)


class TestTheCommandGroup:
    def test_co_slack_has_the_inbox_verbs_and_says_experimental(self):
        import typer.main
        from typer.testing import CliRunner

        from connectonion.cli.main import app

        group = typer.main.get_command(app).commands["slack"]
        assert {"listen", "receive", "send", "reply", "done", "check", "ls", "chats", "log",
                "consume", "edit", "delete", "react"} <= set(group.commands)
        page = CliRunner().invoke(app, ["slack", "--help"], env={"COLUMNS": "200"}).output
        assert "Experimental" in re.sub(r"\x1b\[[0-9;]*m", "", page)

    def test_edit_names_slacks_endpoint_not_feishus(self, bot, monkeypatch, capsys):
        from connectonion.cli.commands import listen_commands

        monkeypatch.setattr(listen_commands, "provider", lambda name: bot)

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_edit("slack", "C1:1.2", "x")

        assert exit_.value.code == 1
        err = capsys.readouterr().err
        assert "chat.update" in err and "/im/v1" not in err

    def test_every_slack_verb_has_a_next_step(self):
        from connectonion.cli.commands.command_tips import NEXT

        for verb in ("listen", "receive", "send", "reply", "done", "edit", "delete", "react",
                     "check", "ls", "chats", "log", "consume"):
            assert f"co slack {verb}" in NEXT
