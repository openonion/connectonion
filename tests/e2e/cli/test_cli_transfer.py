"""Tests for the CLI transfer command (``co transfer``).

What it tests:
- TestGuards: the checks that run before any money can move
  - test_zero_amount_never_reaches_the_network
  - test_negative_amount_never_reaches_the_network
  - test_amount_over_balance_is_refused_before_posting
  - test_unauthenticated_is_refused_before_posting
- TestTransfer: the successful path and what it reports
  - test_successful_transfer_posts_the_expected_body
  - test_output_shows_both_addresses_amount_and_balance_change
  - test_memo_is_omitted_when_not_given
- TestFailures: the backend said no, or the network did
  - test_backend_detail_is_shown_to_the_user
  - test_unreadable_balance_does_not_block_the_transfer
  - test_network_error_warns_that_the_state_is_unknown

Components under test:
- connectonion.cli.commands.transfer_commands.handle_transfer
"""

from unittest.mock import Mock, patch

import requests

from connectonion.cli.commands import transfer_commands


ADDR = "0xcb2f254591e170943db71ab8f25ba2875c0188a319b1b9950a92cec022bc8a2d"
MINE = "0x10e68f6dff39ab1c50cc48ea1c74e7fd6ce7269aa6e8123829b344e57d005508"


def _me(balance):
    """A /api/v1/auth/me response carrying `balance`."""
    response = Mock(status_code=200)
    response.json.return_value = {"balance_usd": balance}
    return response


def _transfer_ok(amount, memo=None):
    """A successful /api/v1/transfers response."""
    response = Mock(status_code=200)
    response.json.return_value = {
        "id": 1,
        "from_address": MINE,
        "to_address": ADDR,
        "amount": amount,
        "memo": memo,
        "created_at": "2026-08-12T10:36:58.380271",
    }
    return response


class TestGuards:
    """Nothing may be posted until these pass."""

    def test_zero_amount_never_reaches_the_network(self):
        with patch.object(transfer_commands.requests, "post") as post:
            assert transfer_commands.handle_transfer(ADDR, 0) is False
            post.assert_not_called()

    def test_negative_amount_never_reaches_the_network(self):
        with patch.object(transfer_commands.requests, "post") as post:
            assert transfer_commands.handle_transfer(ADDR, -5) is False
            post.assert_not_called()

    def test_unauthenticated_is_refused_before_posting(self):
        with patch.object(transfer_commands, "load_api_key", return_value=None), \
             patch.object(transfer_commands.requests, "post") as post:
            assert transfer_commands.handle_transfer(ADDR, 5) is False
            post.assert_not_called()

    def test_amount_over_balance_is_refused_before_posting(self):
        with patch.object(transfer_commands, "load_api_key", return_value="k"), \
             patch.object(transfer_commands.requests, "get", return_value=_me(3.00)), \
             patch.object(transfer_commands.requests, "post") as post:
            assert transfer_commands.handle_transfer(ADDR, 5.00) is False
            post.assert_not_called()


class TestTransfer:
    """The path where the money actually moves."""

    def test_successful_transfer_posts_the_expected_body(self):
        with patch.object(transfer_commands, "load_api_key", return_value="k"), \
             patch.object(transfer_commands.requests, "get", return_value=_me(100.0)), \
             patch.object(transfer_commands.requests, "post", return_value=_transfer_ok(5.0, "rent")) as post:
            assert transfer_commands.handle_transfer(ADDR, 5.0, memo="rent") is True

        body = post.call_args.kwargs["json"]
        assert body == {"to": ADDR, "amount": 5.0, "memo": "rent"}
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer k"

    def test_memo_is_omitted_when_not_given(self):
        with patch.object(transfer_commands, "load_api_key", return_value="k"), \
             patch.object(transfer_commands.requests, "get", return_value=_me(100.0)), \
             patch.object(transfer_commands.requests, "post", return_value=_transfer_ok(5.0)) as post:
            transfer_commands.handle_transfer(ADDR, 5.0)

        assert "memo" not in post.call_args.kwargs["json"]

    def test_output_shows_both_addresses_amount_and_balance_change(self, capsys):
        balances = [_me(100.0), _me(95.0)]
        with patch.object(transfer_commands, "load_api_key", return_value="k"), \
             patch.object(transfer_commands.requests, "get", side_effect=balances), \
             patch.object(transfer_commands.requests, "post", return_value=_transfer_ok(5.0)):
            transfer_commands.handle_transfer(ADDR, 5.0)

        out = capsys.readouterr().out
        assert "0x10e6...5508" in out
        assert "0xcb2f...8a2d" in out
        assert "$5.00" in out
        assert "$100.00" in out and "$95.00" in out


class TestFailures:
    """A refusal must say why, and an unknown outcome must not read as success."""

    def test_backend_detail_is_shown_to_the_user(self, capsys):
        refused = Mock(status_code=400)
        refused.json.return_value = {"detail": "Insufficient balance"}
        with patch.object(transfer_commands, "load_api_key", return_value="k"), \
             patch.object(transfer_commands.requests, "get", return_value=_me(100.0)), \
             patch.object(transfer_commands.requests, "post", return_value=refused):
            assert transfer_commands.handle_transfer(ADDR, 5.0) is False

        assert "Insufficient balance" in capsys.readouterr().out

    def test_unreadable_balance_does_not_block_the_transfer(self):
        """A decoration that fails must not fail the thing it decorates."""
        with patch.object(transfer_commands, "load_api_key", return_value="k"), \
             patch.object(transfer_commands.requests, "get",
                          side_effect=requests.RequestException("boom")), \
             patch.object(transfer_commands.requests, "post", return_value=_transfer_ok(5.0)):
            assert transfer_commands.handle_transfer(ADDR, 5.0) is True

    def test_network_error_warns_that_the_state_is_unknown(self, capsys):
        """The POST may have landed. Do not imply nothing happened."""
        with patch.object(transfer_commands, "load_api_key", return_value="k"), \
             patch.object(transfer_commands.requests, "get", return_value=_me(100.0)), \
             patch.object(transfer_commands.requests, "post",
                          side_effect=requests.RequestException("timeout")):
            assert transfer_commands.handle_transfer(ADDR, 5.0) is False

        assert "--list" in capsys.readouterr().out
