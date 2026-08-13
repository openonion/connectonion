"""Unit tests for the phone notification tool and `co phone`.

LLM-Note: Tests for notify_owner / set_owner_phone / get_owner_phone

What it tests:
- Reaching the owner's phone through oo-api, and every way it can fail

Components under test:
- Module: useful_tools/phone, cli/commands/phone_commands
"""

import sys

import pytest

from connectonion.useful_tools.phone import get_owner_phone, notify_owner, set_owner_phone

phone = sys.modules["connectonion.useful_tools.phone"]


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {"content-type": "application/json"}
        self.text = text

    def json(self):
        return self._payload


@pytest.fixture
def authed(monkeypatch):
    monkeypatch.setenv("OPENONION_API_KEY", "test-key")


def test_a_normal_notification_goes_out_as_a_text(authed, monkeypatch):
    posted = {}

    def fake_post(url, json, headers, timeout):
        posted.update(url=url, json=json, headers=headers)
        return FakeResponse(200, {"sid": "SM1", "to": "+61435525634",
                                  "channel": "sms", "cost_usd": 0.06})

    monkeypatch.setattr(phone.requests, "post", fake_post)

    result = notify_owner("Stuck on AllEvents verification")

    assert result["success"] is True
    assert posted["json"] == {"message": "Stuck on AllEvents verification", "channel": "sms"}
    assert posted["headers"]["Authorization"] == "Bearer test-key"


def test_urgent_escalates_to_a_voice_call(authed, monkeypatch):
    """The whole reason phone exists is the case email cannot cover, and a
    ringing phone is the only thing that gets through a silent one."""
    posted = {}
    monkeypatch.setattr(
        phone.requests, "post",
        lambda url, json, headers, timeout: (posted.update(json=json),
                                             FakeResponse(200, {"channel": "voice"}))[1],
    )

    notify_owner("Deploy is blocked and I cannot continue", urgent=True)

    assert posted["json"]["channel"] == "voice"


def test_no_number_configured_says_so_rather_than_failing_vaguely(authed, monkeypatch):
    monkeypatch.setattr(
        phone.requests, "post",
        lambda url, json, headers, timeout: FakeResponse(
            400, {"detail": "No phone number is set for this account."}),
    )

    result = notify_owner("hello")

    assert result["success"] is False
    assert "No phone number is set" in result["error"]


def test_a_rate_limited_notification_keeps_the_retry_delay(authed, monkeypatch):
    """The agent has to know it was throttled AND for how long, or it will
    either loop or give up — the two failure modes the cooldown exists to stop."""
    monkeypatch.setattr(
        phone.requests, "post",
        lambda url, json, headers, timeout: FakeResponse(
            429,
            {"detail": "A notification was already sent to this account less than 5 minutes ago."},
            headers={"content-type": "application/json", "Retry-After": "240"},
        ),
    )

    result = notify_owner("again")

    assert result["success"] is False
    assert "240" in result["error"]


def test_no_api_key_points_at_co_auth_instead_of_calling(monkeypatch):
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)

    def must_not_run(*args, **kwargs):
        raise AssertionError("called the backend with no key")

    monkeypatch.setattr(phone.requests, "post", must_not_run)

    result = notify_owner("hello")

    assert result["success"] is False
    assert "co auth login" in result["error"]


def test_setting_a_number_returns_what_the_server_stored(authed, monkeypatch):
    put = {}
    monkeypatch.setattr(
        phone.requests, "put",
        lambda url, json, headers, timeout: (put.update(json=json),
                                             FakeResponse(200, {"phone": "+61435525634"}))[1],
    )

    result = set_owner_phone("+61435525634")

    assert result["success"] is True
    assert put["json"] == {"phone": "+61435525634"}


def test_an_unset_number_reads_as_not_configured(authed, monkeypatch):
    monkeypatch.setattr(
        phone.requests, "get",
        lambda url, headers, timeout: FakeResponse(200, {"phone": None, "configured": False}),
    )

    result = get_owner_phone()

    assert result["success"] is True
    assert result["configured"] is False


class TestTheCommand:
    def test_a_failed_notify_exits_nonzero(self, monkeypatch):
        from connectonion.cli.commands import phone_commands

        monkeypatch.setattr(
            phone_commands, "notify_owner",
            lambda message, urgent: {"success": False, "error": "No phone number is set."},
        )

        with pytest.raises(SystemExit) as exc:
            phone_commands.handle_phone_notify("hello")

        assert exc.value.code == 1

    def test_no_number_set_tells_you_the_command_to_set_one(self, monkeypatch, capsys):
        """A person running `co phone` with nothing configured should leave with
        the next command, not with a blank."""
        from connectonion.cli.commands import phone_commands

        monkeypatch.setattr(
            phone_commands, "get_owner_phone",
            lambda: {"success": True, "phone": None, "configured": False},
        )

        phone_commands.handle_phone_number()

        printed = capsys.readouterr().out
        assert "co phone number" in printed
        assert "email" in printed
