"""Unit tests for the Discord outbound tool.

LLM-Note: Tests for send_discord and `co discord send`

What it tests:
- Posting as a bot and through a webhook, and every way it can fail

Components under test:
- Module: useful_tools/discord, cli/commands/discord_commands
"""

import sys

import pytest

from connectonion.useful_tools.discord import send_discord

discord = sys.modules["connectonion.useful_tools.discord"]

WEBHOOK = "https://discord.com/api/webhooks/123/abcSECRETtoken"


class FakeResponse:
    def __init__(self, status_code, payload=None, raises=False):
        self.status_code = status_code
        self._payload = payload
        self._raises = raises

    def json(self):
        if self._raises:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "botTOKEN123")


def test_a_channel_id_posts_as_the_bot(bot, monkeypatch):
    posted = {}

    def fake_post(url, json, headers, timeout):
        posted.update(url=url, json=json, headers=headers)
        return FakeResponse(200, {"id": "999"})

    monkeypatch.setattr(discord.requests, "post", fake_post)

    result = send_discord("42", "1.6.0 is out")

    assert result == {"success": True, "message_id": "999", "channel": "42"}
    assert posted["url"] == "https://discord.com/api/v10/channels/42/messages"
    assert posted["headers"]["Authorization"] == "Bot botTOKEN123"


def test_a_webhook_url_posts_without_a_token(monkeypatch):
    """The release path uses a webhook, and a webhook needs no bot at all."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    posted = {}

    def fake_post(url, json, headers, timeout):
        posted.update(url=url, headers=headers)
        return FakeResponse(204, raises=True)

    monkeypatch.setattr(discord.requests, "post", fake_post)

    result = send_discord(WEBHOOK, "1.6.0 is out")

    assert result["success"] is True
    assert posted["url"] == WEBHOOK
    assert "Authorization" not in posted["headers"]


def test_the_release_note_that_broke_the_1_6_0_announcement_goes_through(monkeypatch):
    """#816: `curl -d "{...}"` broke on backtick and backslash quoting and Discord
    answered 50109 invalid JSON. Serialising in the library cannot make that
    mistake — the characters must reach Discord unmangled."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    posted = {}
    monkeypatch.setattr(
        discord.requests, "post",
        lambda url, json, headers, timeout: (posted.update(json=json),
                                             FakeResponse(204, raises=True))[1],
    )

    nasty = 'Run `co discord send` with a path C:\\Users\\x and a "quote" — 100% done'
    send_discord(WEBHOOK, nasty)

    assert posted["json"]["content"] == nasty


def test_a_user_agent_is_always_sent(monkeypatch):
    """#816: python urllib got 403 because Discord rejects its default
    User-Agent. Ours must never be the default."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    posted = {}
    monkeypatch.setattr(
        discord.requests, "post",
        lambda url, json, headers, timeout: (posted.update(headers=headers),
                                             FakeResponse(204, raises=True))[1],
    )

    send_discord(WEBHOOK, "hello")

    assert posted["headers"]["User-Agent"] == "connectonion"


def test_discords_own_reason_and_code_survive(bot, monkeypatch):
    """50109 and "Unknown Channel" are different problems with different fixes."""
    monkeypatch.setattr(
        discord.requests, "post",
        lambda url, json, headers, timeout: FakeResponse(
            404, {"message": "Unknown Channel", "code": 10003}),
    )

    result = send_discord("42", "hello")

    assert result["success"] is False
    assert "Unknown Channel" in result["error"]
    assert "10003" in result["error"]


def test_a_webhook_url_never_comes_back_in_the_result(monkeypatch):
    """The URL is itself the credential. It must not land in a log line or an
    error an agent might repeat."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr(
        discord.requests, "post",
        lambda url, json, headers, timeout: FakeResponse(400, {"message": "Bad", "code": 50109}),
    )

    result = send_discord(WEBHOOK, "hello")

    assert "abcSECRETtoken" not in str(result)
    assert result["channel"] == "webhook"


def test_a_successful_webhook_post_does_not_echo_the_url_either(monkeypatch):
    """The failure path redacts it; so must the success path. A result gets
    logged, printed, and repeated back by an agent — success is the case that
    happens most often."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.setattr(
        discord.requests, "post",
        lambda url, json, headers, timeout: FakeResponse(204, raises=True),
    )

    result = send_discord(WEBHOOK, "1.6.0 is out")

    assert result["success"] is True
    assert "abcSECRETtoken" not in str(result)
    assert result["channel"] == "webhook"


def test_a_transport_error_does_not_leak_the_webhook(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    def blow_up(url, json, headers, timeout):
        raise discord.requests.ConnectionError(f"failed connecting to {WEBHOOK}")

    monkeypatch.setattr(discord.requests, "post", blow_up)

    result = send_discord(WEBHOOK, "hello")

    assert result["success"] is False
    assert "abcSECRETtoken" not in str(result)
    assert "ConnectionError" in result["error"]


def test_the_bot_token_is_never_echoed_back(bot, monkeypatch):
    monkeypatch.setattr(
        discord.requests, "post",
        lambda url, json, headers, timeout: FakeResponse(
            401, {"message": "Invalid token botTOKEN123", "code": 50014}),
    )

    result = send_discord("42", "hello")

    assert "botTOKEN123" not in result["error"]
    assert "[redacted]" in result["error"]


def test_a_message_over_the_limit_is_refused_here_not_by_discord(monkeypatch):
    """Discord rejects the whole post above 2000 characters rather than
    truncating, so a long release note would silently not appear."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    def must_not_run(*args, **kwargs):
        raise AssertionError("sent an over-length message to Discord")

    monkeypatch.setattr(discord.requests, "post", must_not_run)

    result = send_discord(WEBHOOK, "x" * 2001)

    assert result["success"] is False
    assert "2000" in result["error"]
    assert "2001" in result["error"]


def test_no_token_and_no_webhook_says_how_to_get_one(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)

    def must_not_run(*args, **kwargs):
        raise AssertionError("called Discord with no credential")

    monkeypatch.setattr(discord.requests, "post", must_not_run)

    result = send_discord("42", "hello")

    assert result["success"] is False
    assert "DISCORD_BOT_TOKEN" in result["error"]
    assert "developers/applications" in result["error"]


class TestTheCommand:
    def test_a_refused_post_exits_nonzero(self, monkeypatch):
        """The release path has to be able to tell the announcement did not go out
        — #300 shipped a post with a blank download count and nobody noticed."""
        from connectonion.cli.commands import discord_commands

        monkeypatch.setattr(
            discord_commands, "send_discord",
            lambda channel, message: {"success": False, "error": "Discord refused", "channel": "42"},
        )

        with pytest.raises(SystemExit) as exc:
            discord_commands.handle_discord_send("42", "hello")

        assert exc.value.code == 1

    def test_a_successful_post_exits_zero(self, monkeypatch):
        from connectonion.cli.commands import discord_commands

        monkeypatch.setattr(
            discord_commands, "send_discord",
            lambda channel, message: {"success": True, "message_id": "9", "channel": "42"},
        )

        assert discord_commands.handle_discord_send("42", "hello") == 0
