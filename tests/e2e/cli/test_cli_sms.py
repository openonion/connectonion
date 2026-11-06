"""CLI routing tests for the encrypted SMS inbox."""

from unittest.mock import patch

from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()


def test_bare_sms_shows_inbox_without_mutating_it():
    with patch("connectonion.cli.commands.sms_commands.handle_sms_inbox") as handler:
        result = runner.invoke(app, ["sms"])

    assert result.exit_code == 0
    handler.assert_called_once_with()


def test_sms_pair_routes_secure_defaults():
    with patch("connectonion.cli.commands.sms_commands.handle_sms_pair") as handler:
        result = runner.invoke(app, ["sms", "pair"])

    assert result.exit_code == 0
    handler.assert_called_once_with(expires=600, wait=True, json_output=False)


def test_sms_pair_json_never_enters_interactive_confirmation():
    with patch("connectonion.cli.commands.sms_commands.handle_sms_pair") as handler:
        result = runner.invoke(app, ["sms", "pair", "--json"])

    assert result.exit_code == 0
    handler.assert_called_once_with(expires=600, wait=False, json_output=True)


def test_sms_inbox_routes_machine_readable_pending_filter():
    with patch("connectonion.cli.commands.sms_commands.handle_sms_inbox") as handler:
        result = runner.invoke(app, ["sms", "inbox", "-n", "25", "--pending", "--json"])

    assert result.exit_code == 0
    handler.assert_called_once_with(last=25, pending=True, json_output=True)


def test_sms_devices_revoke_requires_explicit_target():
    with patch("connectonion.cli.commands.sms_commands.handle_sms_revoke") as handler:
        result = runner.invoke(
            app,
            ["sms", "devices", "revoke", "57de9ae4-cd67-447b-a6e4-f4c59dc4183a", "--yes"],
        )

    assert result.exit_code == 0
    handler.assert_called_once_with("57de9ae4-cd67-447b-a6e4-f4c59dc4183a", yes=True)


def _pair_with_phone_answer(answer: str):
    pairing = {
        "id": "bf82a36b-b380-4198-a8d8-3138a3e7cd55",
        "recipient": "0x" + "ab" * 32,
        "pairing_link": "openonion://sms/pair?v=2&id=bf82a36b",
        "expires_at": "2026-11-03T00:00:00Z",
    }
    pending = {
        "status": "pending",
        "device_public_key": "ZGV2aWNl",
        "device": {"device_name": "Google Pixel 8"},
    }
    with (
        patch("connectonion.useful_tools.sms.create_sms_pairing", return_value=pairing),
        patch("connectonion.useful_tools.sms.get_sms_pairing", return_value=pending),
        patch("connectonion.useful_tools.sms.pairing_confirmation_code", return_value="482913"),
        patch("connectonion.useful_tools.sms.confirm_sms_pairing") as confirm,
    ):
        result = runner.invoke(app, ["sms", "pair"], input=answer)
    return result, confirm


def test_sms_pair_enter_approves_the_phone_showing_the_code():
    result, confirm = _pair_with_phone_answer("\n")

    assert result.exit_code == 0, result.output
    assert "482 913" in result.output
    assert "Google Pixel 8 is connected" in result.output
    confirm.assert_called_once()


def test_sms_pair_n_refuses_without_approving():
    result, confirm = _pair_with_phone_answer("n\n")

    assert result.exit_code == 1
    confirm.assert_not_called()
