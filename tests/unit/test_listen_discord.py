"""Discord Gateway adapter fixtures and failure boundaries."""

import asyncio
import json

import pytest

from connectonion.listen.discord import Discord, Reconnect


MESSAGE = {
    "id": "123456789012345678",
    "channel_id": "234567890123456789",
    "guild_id": "345678901234567890",
    "author": {"id": "456789012345678901", "bot": False},
    "content": "check the failed deployment",
    "mentions": [{"id": "999999999999999999"}],
    "timestamp": "2026-09-05T05:00:00.000000+00:00",
}


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "discord-secret-token")
    value = Discord()
    value._me_id = "999999999999999999"
    return value


def test_message_create_normalizes_and_detects_the_current_bot(bot):
    message = bot.to_message(MESSAGE)

    assert message.to_dict() == {
        "id": "123456789012345678",
        "chat": "234567890123456789",
        "thread": None,
        "sender": "456789012345678901",
        "text": "check the failed deployment",
        "mentioned": True,
        "at": "2026-09-05T05:00:00.000000+00:00",
    }


def test_dm_is_addressed_but_unmentioned_guild_message_is_not(bot):
    dm = {**MESSAGE, "guild_id": None, "mentions": []}
    guild = {**MESSAGE, "mentions": []}

    assert bot.to_message(dm).mentioned is True
    assert bot.to_message(guild).mentioned is False


@pytest.mark.parametrize(
    "change",
    [
        {"author": {"id": "456", "bot": True}},
        {"webhook_id": "789"},
        {"author": {"id": "999999999999999999", "bot": False}},
        {"id": ""},
    ],
)
def test_bot_webhook_self_and_malformed_events_are_ignored(bot, change):
    assert bot.to_message({**MESSAGE, **change}) is None


def test_identify_and_resume_carry_the_minimum_state(bot):
    identify = bot._authentication_payload()
    assert identify["op"] == 2
    assert identify["d"]["token"] == "discord-secret-token"
    assert identify["d"]["intents"] & (1 << 15)

    bot._session_id = "session"
    bot._sequence = 42
    resume = bot._authentication_payload()
    assert resume == {
        "op": 6,
        "d": {
            "token": "discord-secret-token",
            "session_id": "session",
            "seq": 42,
        },
    }


@pytest.mark.asyncio
async def test_gateway_dispatches_before_reconnect(bot):
    mailbox = FakeMailbox()
    socket = FakeSocket(
        [
            {"op": 10, "d": {"heartbeat_interval": 60000}},
            {
                "op": 0,
                "t": "READY",
                "s": 1,
                "d": {
                    "session_id": "session",
                    "resume_gateway_url": "wss://resume.discord.test",
                    "user": {"id": "999999999999999999"},
                },
            },
            {"op": 0, "t": "MESSAGE_CREATE", "s": 2, "d": MESSAGE},
            {"op": 7, "d": None},
        ]
    )

    with pytest.raises(Reconnect):
        await bot._session(socket, mailbox, raw=False)

    assert bot._sequence == 2
    assert bot._resume_url == "wss://resume.discord.test"
    assert mailbox.messages[0].id == MESSAGE["id"]
    assert json.loads(socket.sent[0])["op"] == 2


def test_send_retries_one_rate_limit_and_never_echoes_token(bot, monkeypatch):
    responses = [Response(429, {"retry_after": 0}), Response(200, {"id": "sent-id"})]
    posted = []
    monkeypatch.setattr(
        "connectonion.listen.discord.requests.post",
        lambda url, **kwargs: posted.append((url, kwargs)) or responses.pop(0),
    )
    monkeypatch.setattr("connectonion.listen.discord.time.sleep", lambda _: None)

    assert bot.send("234", "hello", reply_to="123") == "sent-id"
    assert len(posted) == 2
    assert posted[0][1]["json"]["message_reference"]["message_id"] == "123"
    assert "discord-secret-token" not in repr(bot._result)


def test_send_rejects_overlong_content_without_network(bot, monkeypatch):
    monkeypatch.setattr(
        "connectonion.listen.discord.requests.post",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("network called")),
    )
    with pytest.raises(RuntimeError, match="2000"):
        bot.send("234", "x" * 2001)


class FakeMailbox:
    def __init__(self):
        self.messages = []
        self.logs = []

    def deliver(self, message, raw=False):
        self.messages.append(message)
        return True

    def log(self, line):
        self.logs.append(line)


class FakeSocket:
    def __init__(self, payloads):
        self.payloads = [json.dumps(value) for value in payloads]
        self.sent = []

    async def recv(self):
        return self.payloads.pop(0)

    async def send(self, value):
        self.sent.append(value)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.payloads:
            raise StopAsyncIteration
        return self.payloads.pop(0)


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self.payload = payload

    def json(self):
        return self.payload
