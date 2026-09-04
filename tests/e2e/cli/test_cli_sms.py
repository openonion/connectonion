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
