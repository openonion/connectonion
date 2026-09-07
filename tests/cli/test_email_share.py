"""co email share/unshare: let another account act as one of your addresses,
without moving it (connectonion#1137). Companion to openonion/oo-api#167.
"""

from unittest.mock import Mock, patch

import pytest
import typer

from connectonion.cli.commands import email_commands


def _resp(ok=True, json_data=None, status=200):
    r = Mock()
    r.ok = ok
    r.status_code = status
    r.json.return_value = json_data
    r.headers = {"content-type": "application/json"}
    r.text = ""
    return r


# --- _parse_capabilities ------------------------------------------------


def test_parses_both_capabilities():
    assert email_commands._parse_capabilities("send,read") == {
        "can_send": True, "can_read": True,
    }


def test_parses_one_capability():
    assert email_commands._parse_capabilities("send") == {
        "can_send": True, "can_read": False,
    }


def test_an_unknown_capability_exits_before_any_request(capsys):
    with pytest.raises(typer.Exit):
        email_commands._parse_capabilities("delete")
    assert "Unknown capability" in capsys.readouterr().out


def test_an_empty_capability_list_exits(capsys):
    with pytest.raises(typer.Exit):
        email_commands._parse_capabilities("")
    assert "at least one of" in capsys.readouterr().out


# --- handle_email_share: granting ---------------------------------------


def test_sharing_posts_the_parsed_capabilities():
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "post",
                      return_value=_resp(json_data={
                          "address": "rental@mail.openonion.ai",
                          "grantee_public_key": "0x" + "b" * 64,
                          "can_send": True, "can_read": False,
                      })) as post:
        email_commands.handle_email_share(
            "rental@mail.openonion.ai", with_="0x" + "b" * 64, can="send",
        )

    payload = post.call_args.kwargs["json"]
    assert payload == {
        "address": "rental@mail.openonion.ai",
        "grantee": "0x" + "b" * 64,
        "can_send": True,
        "can_read": False,
    }


def test_sharing_prints_the_unshare_command(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "post",
                      return_value=_resp(json_data={
                          "address": "rental@mail.openonion.ai",
                          "can_send": True, "can_read": False,
                      })):
        email_commands.handle_email_share(
            "rental@mail.openonion.ai", with_="alice@mail.openonion.ai", can="send",
        )
    out = capsys.readouterr().out
    assert "co email unshare rental@mail.openonion.ai --with alice@mail.openonion.ai" in out


def test_missing_arguments_exits_before_any_request():
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "post") as post:
        with pytest.raises(typer.Exit):
            email_commands.handle_email_share("rental@mail.openonion.ai")
    post.assert_not_called()


def test_share_api_failure_exits_1(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "post",
                      return_value=_resp(ok=False, status=403,
                                         json_data={"detail": "not one of your email addresses."})):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_share(
                "rental@mail.openonion.ai", with_="0x" + "b" * 64, can="send",
            )
    assert exc_info.value.exit_code == 1
    assert "not one of your" in capsys.readouterr().out


def test_no_auth_exits_before_any_request():
    with patch.object(email_commands, "load_api_key", return_value=None), \
         patch.object(email_commands.requests, "post") as post:
        with pytest.raises(typer.Exit):
            email_commands.handle_email_share(
                "rental@mail.openonion.ai", with_="0x" + "b" * 64, can="send",
            )
    post.assert_not_called()


# --- handle_email_share: --list -----------------------------------------


def test_list_shows_both_directions(capsys):
    body = {
        "granted_by_me": [{
            "address": "rental@mail.openonion.ai",
            "grantee_public_key": "0x" + "b" * 64,
            "can_send": True, "can_read": False,
        }],
        "granted_to_me": [{
            "address": "leads@mail.openonion.ai",
            "owner_public_key": "0x" + "c" * 64,
            "can_send": False, "can_read": True,
        }],
    }
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", return_value=_resp(json_data=body)) as get:
        email_commands.handle_email_share(list_=True)

    out = capsys.readouterr().out
    assert "rental@mail.openonion.ai" in out
    assert "leads@mail.openonion.ai" in out
    assert get.call_args.args[0].endswith("/api/v1/email/share")


def test_list_with_nothing_shared_either_way_is_not_an_error(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get",
                      return_value=_resp(json_data={"granted_by_me": [], "granted_to_me": []})):
        email_commands.handle_email_share(list_=True)  # must NOT raise
    out = capsys.readouterr().out
    assert "none" in out


# --- handle_email_unshare -------------------------------------------------


def test_unshare_deletes_the_grant():
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "delete",
                      return_value=_resp(json_data={"success": True, "revoked": True})) as delete:
        email_commands.handle_email_unshare(
            "rental@mail.openonion.ai", with_="0x" + "b" * 64,
        )
    url = delete.call_args.args[0]
    assert url.endswith(f"/api/v1/email/share/rental@mail.openonion.ai/0x{'b' * 64}")


def test_unshare_api_failure_exits_1(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "delete",
                      return_value=_resp(ok=False, status=404,
                                         json_data={"detail": "No active grant."})):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_unshare(
                "rental@mail.openonion.ai", with_="0x" + "b" * 64,
            )
    assert exc_info.value.exit_code == 1
    assert "No active grant" in capsys.readouterr().out
