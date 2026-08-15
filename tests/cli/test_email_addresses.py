"""co email addresses: the account can finally see what it owns (#1019).

The ownership 403 on `co email send --from` named a problem no command could
answer. Now the listing exists, the empty case is not an error, and the 403
message ends by naming the command that answers it.
"""

import sys
from unittest.mock import Mock, patch

import pytest
import typer

from connectonion.cli.commands import email_commands
import connectonion.useful_tools.send_email  # noqa: F401 — the real module, past the package re-exports

_send_module = sys.modules["connectonion.useful_tools.send_email"]


def _resp(ok=True, json_data=None, status=200):
    r = Mock()
    r.ok = ok
    r.status_code = status
    r.json.return_value = json_data
    r.headers = {"content-type": "application/json"}
    r.text = ""
    return r


ADDRESSES = {
    "addresses": [
        {"id": 1, "address": "0xabc123@mail.openonion.ai", "is_default": True, "created_at": "2026-07-01T00:00:00"},
        {"id": 2, "address": "aaron@openonion.ai", "is_default": False, "created_at": "2026-08-01T00:00:00"},
    ]
}


def test_lists_addresses_and_marks_the_default(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", return_value=_resp(json_data=ADDRESSES)):
        email_commands.handle_email_addresses()
    out = capsys.readouterr().out
    assert "0xabc123@mail.openonion.ai\tdefault" in out
    assert "aaron@openonion.ai\t" in out
    assert "co email send" in out and "--from <address>" in out  # next step named


def test_no_addresses_is_an_answer_not_an_error(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", return_value=_resp(json_data={"addresses": []})):
        email_commands.handle_email_addresses()  # must NOT raise
    assert "co email name <name>" in capsys.readouterr().out


def test_api_failure_exits_1(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", return_value=_resp(ok=False, status=500, json_data={"detail": "boom"})):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_addresses()
    assert exc_info.value.exit_code == 1


def test_ownership_403_names_the_addresses_command(capsys):
    failed = {"success": False, "error": "nobody@mail.openonion.ai is not one of this account's email addresses."}
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(_send_module, "send_email", return_value=failed):
        with pytest.raises(typer.Exit):
            email_commands.handle_email_send("a@b.com", "s", "m", from_address="nobody@mail.openonion.ai")
    assert "See your addresses: co email addresses" in capsys.readouterr().out
