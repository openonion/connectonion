"""co transfer: sending money is irreversible, so the CLI confirms before posting.

A declined confirmation exits 1 with nothing sent; server failures exit 1 with
the server's message; success prints the new balance and names the next step
(`co transfer list`); listings carry their tip even when piped (#1018).
"""

from unittest.mock import Mock, patch

import pytest
import typer

from connectonion.cli.commands import transfer_commands


def _resp(ok=True, json_data=None, status=200):
    r = Mock()
    r.ok = ok
    r.status_code = status
    r.json.return_value = json_data
    r.headers = {"content-type": "application/json"}
    r.text = ""
    return r


TRANSFER = {
    "id": 7,
    "from_address": "0xaaa",
    "to_address": "0xbbb",
    "amount": 5.0,
    "memo": None,
    "created_at": "2026-08-15T10:00:00",
}


def test_declined_confirm_exits_1_and_sends_nothing():
    with patch.object(transfer_commands, "load_api_key", return_value="tok"), \
         patch.object(transfer_commands.typer, "confirm", return_value=False), \
         patch.object(transfer_commands.requests, "post") as post:
        with pytest.raises(typer.Exit) as exc_info:
            transfer_commands.handle_transfer_send("0xbbb", 5.0)
    assert exc_info.value.exit_code == 1
    post.assert_not_called()


def test_yes_posts_and_prints_balance_and_tip(capsys):
    balance = _resp(json_data={"credits_usd": 10.0, "total_spent_usd": 3.0})
    with patch.object(transfer_commands, "load_api_key", return_value="tok"), \
         patch.object(transfer_commands.requests, "post", return_value=_resp(json_data=TRANSFER)) as post, \
         patch.object(transfer_commands.requests, "get", return_value=balance):
        transfer_commands.handle_transfer_send("0xbbb", 5.0, yes=True)
    out = capsys.readouterr().out
    assert post.call_args.kwargs["json"] == {"to": "0xbbb", "amount": 5.0}
    assert "$7.00" in out                    # 10 credited - 3 spent
    assert "co transfer list" in out         # next step named


def test_server_failure_exits_1_with_server_message(capsys):
    failed = _resp(ok=False, status=500, json_data={"detail": "Insufficient balance. Have $0.10, need $5.00"})
    with patch.object(transfer_commands, "load_api_key", return_value="tok"), \
         patch.object(transfer_commands.requests, "post", return_value=failed):
        with pytest.raises(typer.Exit) as exc_info:
            transfer_commands.handle_transfer_send("0xbbb", 5.0, yes=True)
    assert exc_info.value.exit_code == 1
    assert "Insufficient balance" in capsys.readouterr().out


def test_missing_amount_is_a_usage_error():
    with pytest.raises(typer.Exit) as exc_info:
        transfer_commands.handle_transfer_send("0xbbb", None)
    assert exc_info.value.exit_code == 2


def test_list_carries_its_tip_when_piped(capsys):
    with patch.object(transfer_commands, "load_api_key", return_value="tok"), \
         patch.object(transfer_commands.requests, "get", return_value=_resp(json_data=[TRANSFER])):
        transfer_commands.handle_transfer_list()
    out = capsys.readouterr().out
    assert "0xbbb" in out
    assert "co transfer <address> <amount>" in out


def test_list_sent_asks_the_server_for_sent(capsys):
    with patch.object(transfer_commands, "load_api_key", return_value="tok"), \
         patch.object(transfer_commands.requests, "get", return_value=_resp(json_data=[])) as get:
        transfer_commands.handle_transfer_list(sent=True)
    assert get.call_args.kwargs["params"]["type"] == "sent"
    # Empty history is an answer, not an error — and it still names the next step.
    assert "co transfer <address> <amount>" in capsys.readouterr().out
