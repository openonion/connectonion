"""Unit tests for the Telegram mailbox provider.

LLM-Note: Tests for connectonion.listen.telegram

What it tests:
- A getUpdates update becomes the seven-field Message; ids carry the chat because Telegram's message_id does not
- Group messages count as mentioned only when they @ the bot or reply to it; private chats always
- The poll loop advances the offset, delivers once, and survives a transport error
- send() quotes the received message, honours retry_after once, and never echoes the token

Components under test:
- Module: connectonion/listen/telegram.py
"""

import pytest

from connectonion.listen import telegram as telegram_module
from connectonion.listen.mailbox import Mailbox
from connectonion.listen.telegram import Telegram


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    t = Telegram()
    t._me = {"id": 777, "username": "OpsBot"}
    return t


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def update(*, text="@OpsBot look at the deploy", chat_type="supergroup", entities=None, update_id=10,
           message_id=55, sender=None, reply_to=None, extra=None):
    m = {
        "message_id": message_id,
        "date": 1756808267,
        "chat": {"id": -100123, "type": chat_type},
        "from": sender or {"id": 4242, "is_bot": False, "first_name": "Aaron"},
        "text": text,
    }
    if entities is not None:
        m["entities"] = entities
    if reply_to:
        m["reply_to_message"] = reply_to
    if extra:
        m.update(extra)
    return {"update_id": update_id, "message": m}


def test_a_group_mention_becomes_a_message_whose_id_carries_the_chat(bot):
    message = bot.to_message(update(entities=[{"type": "mention", "offset": 0, "length": 7}]))

    assert message.to_dict() == {
        "id": "-100123.55", "chat": "-100123", "thread": None, "sender": "4242",
        "text": "@OpsBot look at the deploy", "mentioned": True, "at": "2025-09-02T10:17:47Z",
    }


def test_mentioning_someone_else_or_nobody_is_not_mentioning_us(bot):
    other = bot.to_message(update(text="@alice look", entities=[{"type": "mention", "offset": 0, "length": 6}]))
    nobody = bot.to_message(update(text="just chatting"))

    assert other.mentioned is False
    assert nobody.mentioned is False


def test_replying_to_the_bot_counts_as_a_mention(bot):
    message = bot.to_message(update(text="yes do it", reply_to={"message_id": 50, "from": {"id": 777, "is_bot": True}}))
    assert message.mentioned is True


def test_a_command_addressed_to_us_counts(bot):
    message = bot.to_message(update(text="/status@OpsBot", entities=[{"type": "bot_command", "offset": 0, "length": 14}]))
    assert message.mentioned is True


def test_a_private_chat_is_always_addressed_to_us(bot):
    assert bot.to_message(update(text="hi", chat_type="private")).mentioned is True


def test_a_forum_topic_is_the_thread(bot):
    message = bot.to_message(update(extra={"is_topic_message": True, "message_thread_id": 9}))
    assert message.thread == "9"


def test_bots_edits_and_channel_posts_are_dropped_and_media_is_named(bot):
    assert bot.to_message(update(sender={"id": 1, "is_bot": True})) is None
    assert bot.to_message({"update_id": 1, "edited_message": {}}) is None
    photo = update(text=None, extra={"photo": [{"file_id": "x"}]})
    del photo["message"]["text"]
    assert bot.to_message(photo).text == "[photo]"


def test_the_poll_loop_delivers_once_and_advances_the_offset(bot, tmp_path, monkeypatch):
    box = Mailbox("telegram", home=tmp_path / "telegram")
    calls = []
    batches = iter([
        FakeResponse({"ok": True, "result": [update(update_id=10), update(update_id=11, message_id=56)]}),
        FakeResponse({"ok": True, "result": [update(update_id=10)]}),  # a redelivery
        KeyboardInterrupt(),
    ])

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        item = next(batches)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr(telegram_module.requests, "post", fake_post)
    monkeypatch.setattr(telegram_module.requests, "get", lambda url, timeout=None: FakeResponse(
        {"ok": True, "result": {"id": 777, "username": "OpsBot"}}))

    with pytest.raises(KeyboardInterrupt):
        bot.run(box)

    assert [c["offset"] for c in calls] == [None, 12, 12]
    assert [p.name.split("-", 1)[1] for p in box.unread()] == ["-100123.55", "-100123.56"]
    assert "duplicate -100123.55 dropped" in box.logfile.read_text()
    assert "connected as @OpsBot" in box.logfile.read_text()


def test_a_transport_error_in_the_loop_is_logged_and_retried(bot, tmp_path, monkeypatch):
    box = Mailbox("telegram", home=tmp_path / "telegram")
    slept = []
    monkeypatch.setattr(telegram_module.time, "sleep", lambda s: slept.append(s))
    attempts = iter([telegram_module.requests.ConnectionError("boom http://api.telegram.org/bot123:ABC"),
                     KeyboardInterrupt()])

    def fake_post(url, json=None, timeout=None):
        raise next(attempts)

    monkeypatch.setattr(telegram_module.requests, "post", fake_post)
    monkeypatch.setattr(telegram_module.requests, "get", lambda url, timeout=None: FakeResponse(
        {"ok": True, "result": {"id": 777, "username": "OpsBot"}}))

    with pytest.raises(KeyboardInterrupt):
        bot.run(box)

    log = box.logfile.read_text()
    assert "getUpdates failed: Telegram request failed (ConnectionError)" in log
    assert "123:ABC" not in log
    assert slept == [1.0]


def test_reply_quotes_the_received_message(bot, monkeypatch):
    posted = {}

    def fake_post(url, json=None, timeout=None):
        posted.update(url=url, json=json)
        return FakeResponse({"ok": True, "result": {"message_id": 99}})

    monkeypatch.setattr(telegram_module.requests, "post", fake_post)

    assert bot.send("-100123", "fixed", reply_to="-100123.55") == "-100123.99"
    assert posted["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"
    assert posted["json"] == {"chat_id": "-100123", "text": "fixed", "reply_parameters": {"message_id": 55}}


def test_a_rate_limit_is_honoured_once_and_a_refusal_keeps_telegrams_words_minus_the_token(bot, monkeypatch):
    slept = []
    monkeypatch.setattr(telegram_module.time, "sleep", lambda s: slept.append(s))
    responses = iter([
        FakeResponse({"ok": False, "parameters": {"retry_after": 3}}, status_code=429),
        FakeResponse({"ok": False, "description": "Bad Request: chat not found for 123:ABC"}),
    ])
    monkeypatch.setattr(telegram_module.requests, "post", lambda url, json=None, timeout=None: next(responses))

    with pytest.raises(RuntimeError, match=r"chat not found for \[redacted\]"):
        bot.send("-1", "hi")
    assert slept == [3.0]


def test_missing_token_names_botfather_and_check_reports_a_bad_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    (problem,) = Telegram().missing()
    assert "@BotFather" in problem and "TELEGRAM_BOT_TOKEN" in problem

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bad")
    monkeypatch.setattr(telegram_module.requests, "get", lambda url, timeout=None: FakeResponse(
        {"ok": False, "description": "Unauthorized"}, status_code=401))
    (problem,) = Telegram().check()
    assert "Unauthorized" in problem
