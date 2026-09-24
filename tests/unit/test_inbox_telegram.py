"""Unit tests for the Telegram inbox provider.

LLM-Note: Tests for connectonion.inbox.telegram

What it tests:
- A getUpdates update becomes a Message; ids carry the chat because Telegram's message_id does not
- Group messages count as mentioned only when they @ the bot, /command@ it, or reply to it; private chats always
- The poll loop advances the offset, delivers once, survives a transport error, and records its connection
- A revoked token or a second poller ends the listener with ListenerStopped instead of retrying forever
- send() quotes the received message, honours retry_after once, and never echoes the token
- `co telegram` keeps its original `send` and gains the inbox verbs beside it

Components under test:
- Module: connectonion/inbox/telegram.py
- Registration: connectonion/inbox/__init__.py, connectonion/cli/main.py (_inbox_group)
"""

import pytest

from connectonion.inbox import ListenerStopped, provider
from connectonion.inbox import telegram as telegram_module
from connectonion.inbox.store import Inbox
from connectonion.inbox.telegram import Telegram


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    t = Telegram()
    t._me = {"id": 777, "username": "OpsBot"}
    return t


@pytest.fixture
def box(tmp_path):
    return Inbox("telegram", home=tmp_path / "telegram")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


ME = FakeResponse({"ok": True, "result": {"id": 777, "username": "OpsBot"}})


def update(*, text="@OpsBot look at the deploy", chat_type="supergroup", entities=None, update_id=10,
           message_id=55, sender=None, reply_to=None, extra=None):
    m = {
        "message_id": message_id,
        "date": 1756808267,
        "chat": {"id": -100123, "type": chat_type},
        "from": sender or {"id": 4242, "is_bot": False, "first_name": "Aaron", "last_name": "Xi"},
        "text": text,
    }
    if entities is not None:
        m["entities"] = entities
    if reply_to:
        m["reply_to_message"] = reply_to
    if extra:
        m.update(extra)
    return {"update_id": update_id, "message": m}


def scripted(monkeypatch, *items):
    """requests.post answering getMe with ME and every other call from `items`
    in order; an exception in the list is raised. Returns the bodies sent."""
    calls = []
    queue = list(items)

    def fake_post(url, json=None, timeout=None):
        if url.endswith("/getMe"):
            return ME
        calls.append((url.rsplit("/", 1)[1], json))
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(telegram_module.requests, "post", fake_post)
    return calls


class TestAnUpdateBecomesAMessage:
    def test_a_group_mention_becomes_a_message_whose_id_carries_the_chat(self, bot):
        message = bot.to_message(update(entities=[{"type": "mention", "offset": 0, "length": 7}]))

        record = message.to_dict()
        assert record["id"] == "-100123.55"
        assert record["chat"] == "-100123"
        assert record["sender"] == "4242"
        assert record["sender_name"] == "Aaron Xi"
        assert record["text"] == "@OpsBot look at the deploy"
        assert record["kind"] == "text"
        assert record["mentioned"] is True
        assert record["at"] == "2025-09-02T10:17:47Z"

    def test_the_same_message_number_in_two_groups_is_two_messages(self, bot, box):
        first = bot.to_message(update())
        other = update()
        other["message"]["chat"]["id"] = -100999
        second = bot.to_message(other)

        assert box.deliver(first) and box.deliver(second)
        assert len(box.unread()) == 2

    def test_mentioning_someone_else_or_nobody_is_not_mentioning_us(self, bot):
        other = bot.to_message(update(text="@alice look", entities=[{"type": "mention", "offset": 0, "length": 6}]))
        nobody = bot.to_message(update(text="just chatting"))

        assert other.mentioned is False
        assert nobody.mentioned is False

    def test_replying_to_the_bot_counts_as_a_mention_and_is_quoted_as_ours(self, bot):
        message = bot.to_message(update(text="yes do it", reply_to={
            "message_id": 50, "from": {"id": 777, "is_bot": True}, "text": "deploy?"}))

        assert message.mentioned is True
        assert message.quoted == {"id": "-100123.50", "sender": "777", "text": "deploy?",
                                  "kind": "text", "from_me": True}

    def test_replying_to_someone_else_is_quoted_but_not_ours(self, bot):
        message = bot.to_message(update(text="agreed", reply_to={
            "message_id": 49, "from": {"id": 5, "is_bot": False}, "text": "ship it"}))

        assert message.mentioned is False
        assert message.quoted["from_me"] is False

    def test_a_command_addressed_to_us_counts(self, bot):
        message = bot.to_message(update(text="/status@OpsBot",
                                        entities=[{"type": "bot_command", "offset": 0, "length": 14}]))
        assert message.mentioned is True

    def test_a_mention_after_an_emoji_is_still_ours(self, bot):
        """Telegram counts entity offsets in UTF-16 code units: the rocket is
        two units, so offset 3 means "after the emoji and a space"."""
        message = bot.to_message(update(text="🚀 @OpsBot deploy",
                                        entities=[{"type": "mention", "offset": 3, "length": 7}]))
        assert message.mentioned is True

    def test_a_private_chat_is_always_addressed_to_us(self, bot):
        assert bot.to_message(update(text="hi", chat_type="private")).mentioned is True

    def test_a_forum_topic_is_the_thread_and_its_opening_is_not_a_quote(self, bot):
        message = bot.to_message(update(extra={"is_topic_message": True, "message_thread_id": 9},
                                        reply_to={"message_id": 9, "forum_topic_created": {"name": "ops"}}))
        assert message.thread == "9"
        assert message.quoted is None

    def test_bots_edits_and_service_messages_are_dropped(self, bot):
        assert bot.to_message(update(sender={"id": 1, "is_bot": True})) is None
        assert bot.to_message({"update_id": 1, "edited_message": {}}) is None
        joined = update(extra={"new_chat_members": [{"id": 5}]})
        del joined["message"]["text"]
        assert bot.to_message(joined) is None

    def test_media_is_named_and_a_caption_is_kept(self, bot):
        photo = update(extra={"photo": [{"file_id": "x"}]})
        del photo["message"]["text"]
        captioned = update(extra={"voice": {"file_id": "v"}, "caption": "listen to this"})
        del captioned["message"]["text"]

        assert (bot.to_message(photo).text, bot.to_message(photo).kind) == ("[photo]", "photo")
        assert (bot.to_message(captioned).text, bot.to_message(captioned).kind) == ("listen to this", "voice")


class TestTheListener:
    def test_the_poll_loop_delivers_once_and_advances_the_offset(self, bot, box, monkeypatch):
        calls = scripted(
            monkeypatch,
            FakeResponse({"ok": True, "result": [update(update_id=10), update(update_id=11, message_id=56)]}),
            FakeResponse({"ok": True, "result": [update(update_id=10)]}),  # a redelivery
            KeyboardInterrupt(),
        )

        with pytest.raises(KeyboardInterrupt):
            bot.run(box)

        assert [body["offset"] for _, body in calls] == [None, 12, 12]
        assert [p.name.split("-", 1)[1] for p in box.unread()] == ["-100123.55", "-100123.56"]
        log = box.logfile.read_text()
        assert "duplicate -100123.55 dropped" in log
        assert "connected as @OpsBot" in log
        state = box.connection_state()
        assert (state["state"], state["account"]) == ("connected", "@OpsBot")

    def test_a_transport_error_is_logged_retried_and_recorded(self, bot, box, monkeypatch):
        slept = []
        monkeypatch.setattr(telegram_module.time, "sleep", lambda s: slept.append(s))
        scripted(
            monkeypatch,
            FakeResponse({"ok": True, "result": []}),
            telegram_module.requests.ConnectionError("boom http://api.telegram.org/bot123:ABC"),
            KeyboardInterrupt(),
        )

        with pytest.raises(KeyboardInterrupt):
            bot.run(box)

        log = box.logfile.read_text()
        assert "getUpdates failed: Telegram request failed (ConnectionError)" in log
        assert "123:ABC" not in log
        assert slept == [1.0]
        assert box.connection_state()["state"] == "disconnected"

    def test_an_update_it_cannot_read_is_skipped_not_refetched(self, bot, box, monkeypatch):
        calls = scripted(
            monkeypatch,
            FakeResponse({"ok": True, "result": [{"update_id": 20, "message": {"chat": {"id": 1},
                                                  "from": {"id": 2}, "text": "x", "message_id": 3,
                                                  "entities": [{"offset": "not a number",
                                                                "type": "mention"}]}}]}),
            KeyboardInterrupt(),
        )

        with pytest.raises(KeyboardInterrupt):
            bot.run(box)

        assert "update not understood" in box.logfile.read_text()
        assert calls[-1][1]["offset"] == 21

    @pytest.mark.parametrize("status, description, advice", [
        (401, "Unauthorized", "@BotFather"),
        (409, "Conflict: terminated by other getUpdates request", "deleteWebhook"),
    ])
    def test_a_refusal_no_restart_fixes_stops_the_listener(self, bot, box, monkeypatch,
                                                           status, description, advice):
        scripted(monkeypatch, FakeResponse({"ok": False, "description": description}, status_code=status))

        with pytest.raises(ListenerStopped) as stopped:
            bot.run(box)

        assert description in str(stopped.value) and advice in str(stopped.value)
        assert box.connection_state()["state"] == "stopped"


class TestSending:
    def test_reply_quotes_the_received_message(self, bot, monkeypatch):
        posted = {}

        def fake_post(url, json=None, timeout=None):
            posted.update(url=url, json=json)
            return FakeResponse({"ok": True, "result": {"message_id": 99}})

        monkeypatch.setattr(telegram_module.requests, "post", fake_post)

        assert bot.send("-100123", "fixed", reply_to="-100123.55") == "-100123.99"
        assert posted["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"
        assert posted["json"] == {"chat_id": "-100123", "text": "fixed",
                                  "reply_parameters": {"message_id": 55, "allow_sending_without_reply": True}}

    def test_a_rate_limit_is_honoured_once_and_a_refusal_keeps_telegrams_words_minus_the_token(
            self, bot, monkeypatch):
        slept = []
        monkeypatch.setattr(telegram_module.time, "sleep", lambda s: slept.append(s))
        responses = iter([
            FakeResponse({"ok": False, "parameters": {"retry_after": 3}}, status_code=429),
            FakeResponse({"ok": False, "description": "Bad Request: chat not found for 123:ABC"}, 400),
        ])
        monkeypatch.setattr(telegram_module.requests, "post", lambda url, json=None, timeout=None: next(responses))

        with pytest.raises(RuntimeError, match=r"chat not found for \[redacted\]"):
            bot.send("-1", "hi")
        assert slept == [3.0]


class TestSetup:
    def test_the_missing_token_message_is_the_one_co_telegram_send_already_uses(self, monkeypatch):
        from connectonion.useful_tools.telegram import NO_TOKEN

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        assert Telegram().missing() == [NO_TOKEN]
        assert "@BotFather" in NO_TOKEN

    def test_check_reports_a_bad_token_in_telegrams_words(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bad")
        monkeypatch.setattr(telegram_module.requests, "post", lambda url, json=None, timeout=None: FakeResponse(
            {"ok": False, "description": "Unauthorized"}, status_code=401))
        (problem,) = Telegram().check()
        assert "Unauthorized" in problem and "Next:" in problem

    def test_it_is_a_registered_provider(self, monkeypatch):
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
        assert isinstance(provider("telegram"), Telegram)


class TestTheCommandGroup:
    def test_send_is_still_the_original_and_the_inbox_verbs_sit_beside_it(self):
        import typer.main

        from connectonion.cli.main import app

        group = typer.main.get_command(app).commands["telegram"]
        assert {"listen", "receive", "reply", "done", "check", "ls", "chats", "log",
                "consume", "send"} <= set(group.commands)
        # `co telegram send CHAT MESSAGE` keeps its own handler and output.
        assert group.commands["send"].callback.__name__ == "telegram_send"

    def test_edit_names_telegrams_endpoint_not_feishus(self, bot, box, monkeypatch, capsys):
        from connectonion.cli.commands import listen_commands

        monkeypatch.setattr(listen_commands, "provider", lambda name: bot)

        with pytest.raises(SystemExit) as exit_:
            listen_commands.handle_edit("telegram", "-100123.55", "x")

        assert exit_.value.code == 1
        err = capsys.readouterr().err
        assert "editMessageText" in err and "/im/v1" not in err

    def test_reply_goes_to_the_chat_the_message_came_from(self, bot, monkeypatch, tmp_path, capsys):
        from connectonion.cli.commands import listen_commands

        monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path))
        Inbox("telegram").deliver(bot.to_message(update()))
        sent = []

        def fake_post(url, json=None, timeout=None):
            sent.append(json)
            return FakeResponse({"ok": True, "result": {"message_id": 100}})

        monkeypatch.setattr(telegram_module.requests, "post", fake_post)
        monkeypatch.setattr(listen_commands, "provider", lambda name: bot)

        listen_commands.handle_reply("telegram", "-100123.55", "on it")

        assert capsys.readouterr().out.strip() == "-100123.100"
        assert sent == [{"chat_id": "-100123", "text": "on it",
                         "reply_parameters": {"message_id": 55, "allow_sending_without_reply": True}}]
        assert Inbox("telegram").already_replied("-100123.55")
