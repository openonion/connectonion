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
    def __init__(self, payload=None, *, status_code=200, json_error=False):
        self._payload = payload
        self.status_code = status_code
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
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


def test_transport_errors_do_not_return_the_token_bearing_url(bot, monkeypatch):
    def fail(url, json, timeout):
        raise telegram.requests.ConnectionError(f"failed to reach {url}")

    monkeypatch.setattr(telegram.requests, "post", fail)

    result = send_telegram("12345", "hello")

    assert result["success"] is False
    assert "ConnectionError" in result["error"]
    assert "123:ABC" not in repr(result)
    assert "api.telegram.org" not in repr(result)


def test_non_json_and_malformed_success_responses_fail_safely(bot, monkeypatch):
    responses = iter(
        [
            FakeResponse(status_code=502, json_error=True),
            FakeResponse({"ok": True, "result": {}}),
        ]
    )
    monkeypatch.setattr(
        telegram.requests,
        "post",
        lambda url, json, timeout: next(responses),
    )

    non_json = send_telegram("12345", "hello")
    malformed = send_telegram("12345", "hello")

    assert non_json["error"] == "Telegram returned HTTP 502 without JSON."
    assert malformed["error"] == "Telegram returned an invalid success response."
    assert "123:ABC" not in repr((non_json, malformed))


def test_a_server_description_cannot_echo_the_bot_token(bot, monkeypatch):
    monkeypatch.setattr(
        telegram.requests,
        "post",
        lambda url, json, timeout: FakeResponse(
            {"ok": False, "description": "bad token 123:ABC"}
        ),
    )

    result = send_telegram("12345", "hello")

    assert "[redacted]" in result["error"]
    assert "123:ABC" not in repr(result)


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

    def test_terminal_input_is_rendered_as_text_not_rich_markup(
        self, monkeypatch, capsys
    ):
        from connectonion.cli.commands import telegram_commands
        from rich.console import Console

        monkeypatch.setattr(
            telegram_commands,
            "console",
            Console(width=200, color_system=None),
        )
        monkeypatch.setattr(
            telegram_commands,
            "send_telegram",
            lambda chat, message: {
                "success": True,
                "message_id": "[link=https://bad.example]5[/link]",
                "chat": chat,
            },
        )

        telegram_commands.handle_telegram_send("[bold]owner[/bold]", "hello")
        output = capsys.readouterr().out

        assert "[bold]owner[/bold]" in output
        assert "[link=https://bad.example]5[/link]" in output

    def test_terminal_error_is_rendered_as_text_not_rich_markup(
        self, monkeypatch, capsys
    ):
        from connectonion.cli.commands import telegram_commands
        from rich.console import Console

        monkeypatch.setattr(
            telegram_commands,
            "console",
            Console(width=200, color_system=None),
        )
        monkeypatch.setattr(
            telegram_commands,
            "send_telegram",
            lambda chat, message: {
                "success": False,
                "error": "[link=https://bad.example]refused[/link]",
            },
        )

        with pytest.raises(SystemExit):
            telegram_commands.handle_telegram_send("owner", "hello")
        output = capsys.readouterr().out

        assert "[link=https://bad.example]refused[/link]" in output


def test_the_tool_is_available_from_the_public_package():
    import connectonion

    assert connectonion.send_telegram is send_telegram


def test_status_discovers_the_bot_token_without_exposing_it(tmp_path):
    from connectonion.cli.commands.status_commands import _credential_rows

    project = tmp_path / "project"
    home = tmp_path / "home"
    project.mkdir()
    (home / ".co").mkdir(parents=True)
    token = "123:ABC"
    (home / ".co" / "keys.env").write_text(f"TELEGRAM_BOT_TOKEN={token}\n")

    rows = _credential_rows(project_dir=project, home=home, environ={})
    row = next(item for item in rows if item["credential"] == "TELEGRAM_BOT_TOKEN")

    assert row["provider"] == "Telegram"
    assert row["status"] == "discovered · not loaded"
    assert row["source"] == "~/.co/keys.env"
    assert token not in repr(rows)
