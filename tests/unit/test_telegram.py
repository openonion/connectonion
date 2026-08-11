"""Unit tests for the Telegram outbound tool.

LLM-Note: Tests for send_telegram and `co telegram send`

What it tests:
- Sending a message, and every way it can fail without a live bot

Components under test:
- Module: useful_tools/telegram, cli/commands/telegram_commands
"""

import sys

import pytest

from connectonion.useful_tools.telegram import send_telegram

# The package re-exports the function, so the module has to be reached by name.
telegram = sys.modules["connectonion.useful_tools.telegram"]


class FakeResponse:
    def __init__(self, payload, text=""):
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")


def test_a_sent_message_reports_the_id_telegram_gave_it(bot, monkeypatch):
    posted = {}

    def fake_post(url, json, timeout):
        posted.update(url=url, json=json)
        return FakeResponse({"ok": True, "result": {"message_id": 42}})

    monkeypatch.setattr(telegram.requests, "post", fake_post)

    result = send_telegram("12345", "Your agent is stuck on AllEvents")

    assert result == {"success": True, "message_id": 42, "chat": "12345"}
    assert posted["json"] == {"chat_id": "12345", "text": "Your agent is stuck on AllEvents"}


def test_the_token_is_in_the_url_and_never_in_the_body(bot, monkeypatch):
    """Telegram puts the token in the path. It must not also be logged into a
    payload that gets echoed back in an error message."""
    posted = {}

    def fake_post(url, json, timeout):
        posted.update(url=url, json=json)
        return FakeResponse({"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    send_telegram("12345", "hello")

    assert posted["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"
    assert "123:ABC" not in str(posted["json"])


def test_no_token_explains_how_to_get_one_instead_of_crashing(monkeypatch):
    """A missing bot token is a setup problem, and the fix is three steps the
    message should just say."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    def must_not_run(*args, **kwargs):
        raise AssertionError("called Telegram with no token")

    monkeypatch.setattr(telegram.requests, "post", must_not_run)

    result = send_telegram("12345", "hello")

    assert result["success"] is False
    assert "BotFather" in result["error"]
    assert "TELEGRAM_BOT_TOKEN" in result["error"]


def test_telegrams_own_reason_survives_to_the_caller(bot, monkeypatch):
    """"chat not found" and "bot was blocked by the user" are different problems
    with different fixes. Replacing them with "send failed" loses the fix."""
    monkeypatch.setattr(
        telegram.requests, "post",
        lambda url, json, timeout: FakeResponse({"ok": False, "description": "Bad Request: chat not found"}),
    )

    result = send_telegram("99999", "hello")

    assert result["success"] is False
    assert "chat not found" in result["error"]
    assert result["chat"] == "99999"


def test_a_channel_name_is_passed_through_as_given(bot, monkeypatch):
    """@channelname is a valid chat_id to Telegram — it must not be mangled."""
    posted = {}
    monkeypatch.setattr(
        telegram.requests, "post",
        lambda url, json, timeout: (posted.update(json=json),
                                    FakeResponse({"ok": True, "result": {"message_id": 7}}))[1],
    )

    send_telegram("@openonion", "hello")

    assert posted["json"]["chat_id"] == "@openonion"


class TestTheCommand:
    def test_a_refused_send_exits_nonzero(self, monkeypatch):
        """A script that pipes into `co telegram send` has to be able to tell
        that the message did not arrive."""
        from connectonion.cli.commands import telegram_commands

        monkeypatch.setattr(
            telegram_commands, "send_telegram",
            lambda chat, message: {"success": False, "error": "Telegram refused the message: chat not found"},
        )

        with pytest.raises(SystemExit) as exc:
            telegram_commands.handle_telegram_send("99999", "hello")

        assert exc.value.code == 1

    def test_a_successful_send_exits_zero(self, monkeypatch):
        from connectonion.cli.commands import telegram_commands

        monkeypatch.setattr(
            telegram_commands, "send_telegram",
            lambda chat, message: {"success": True, "message_id": 5, "chat": "12345"},
        )

        assert telegram_commands.handle_telegram_send("12345", "hello") == 0
