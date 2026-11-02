"""One account, several mailboxes: say which one, and pick a default.

An account can own more than one address and can be granted read access to
another account's. Until now the inbox merged them into one list that never said
which address a message arrived at, and there was no way to ask for just one.

That ambiguity is not cosmetic. On 2026-09-05 a job application went out
carrying the wrong one of two addresses; the employer's reply was delivered and
stored correctly and simply could not be told apart from — or found among — the
other mailbox's mail. Successful delivery produces no bounce, so nothing
anywhere reported a problem.

The default sender had the same shape of gap: `is_default` existed in the
database, `co email addresses` displayed it, and no command could change it.
"""

import sys
from unittest.mock import Mock, patch

import pytest
import typer
from rich.console import Console

from connectonion.cli.commands import email_commands
import connectonion.useful_tools.get_emails  # noqa: F401 — the real module, past the package re-exports

# `from connectonion.useful_tools import get_emails` binds the FUNCTION the
# package re-exports, not the module, and patching an attribute on it fails
# with a confusing AttributeError. Same trick as test_email_addresses.py.
get_emails_module = sys.modules["connectonion.useful_tools.get_emails"]


def _resp(ok=True, json_data=None, status=200):
    r = Mock()
    r.ok = ok
    r.status_code = status
    r.json.return_value = json_data
    r.headers = {"content-type": "application/json"}
    r.text = ""
    r.raise_for_status = Mock()
    return r


TWO_MAILBOXES = [
    {"id": 486, "from": "xietianle@outlook.com", "to": "aaron@mail.openonion.ai",
     "subject": "deliverability check", "message": "", "timestamp": "2026-09-04T22:53:56", "read": False},
    {"id": 484, "from": "events@example.com", "to": "aaron.xie@mail.openonion.ai",
     "subject": "popular events", "message": "", "timestamp": "2026-09-04T08:29:40", "read": True},
]

ONE_MAILBOX = [TWO_MAILBOXES[0]]


def test_inbox_names_the_mailbox_when_the_page_spans_two(capsys):
    # A wide console so the assertion is about content, not terminal geometry:
    # at 80 columns Rich folds an address across lines and no substring check
    # can tell folding from truncation.
    wide = Console(width=200)
    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(email_commands, "console", wide), \
         patch.object(get_emails_module, "get_emails", return_value=TWO_MAILBOXES):
        email_commands.handle_email_inbox()
    out = capsys.readouterr().out
    assert "aaron@mail.openonion.ai" in out
    assert "aaron.xie@mail.openonion.ai" in out
    assert "--address" in out, "the way to narrow it must be discoverable here"


def test_inbox_omits_the_to_column_for_a_single_mailbox(capsys):
    """Same string on every row is noise, so it must not be spent on a column."""
    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=ONE_MAILBOX):
        email_commands.handle_email_inbox()
    out = capsys.readouterr().out
    assert "--address" not in out


def test_inbox_passes_the_address_filter_through(capsys):
    captured = {}

    def _fake(last=10, offset=0, address=None, **kw):
        captured["address"] = address
        return ONE_MAILBOX

    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", _fake):
        email_commands.handle_email_inbox(address="aaron@mail.openonion.ai")
    assert captured["address"] == "aaron@mail.openonion.ai"


def test_empty_filtered_inbox_says_which_mailbox_was_empty(capsys):
    owned = {"addresses": [{"address": "aaron@mail.openonion.ai", "is_default": True}]}
    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=[]), \
         patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", return_value=_resp(json_data=owned)) as get:
        email_commands.handle_email_inbox(address="aaron@mail.openonion.ai")
    out = capsys.readouterr().out
    assert "no emails at aaron@mail.openonion.ai" in out
    assert "not one of this account's email addresses" not in out
    assert get.call_args.args[0].endswith("/api/v1/email/addresses")
    assert get.call_count == 1


def test_inbox_for_an_address_this_account_does_not_own_exits_nonzero(capsys):
    """The received API returns an empty page for an address it will not confirm.

    That page is not "no mail arrived". `co email default` already refuses an
    address this account does not own; the inbox filter has to do the same,
    and name the addresses the account does own (#2671).
    """
    owned = {"addresses": [
        {"address": "aaron@mail.openonion.ai", "is_default": True},
        {"address": "aaron.xie@mail.openonion.ai", "is_default": False},
    ]}

    def _get(url, **kwargs):
        if str(url).endswith("/api/v1/email/share"):
            return _resp(json_data={"granted_by_me": [], "granted_to_me": []})
        return _resp(json_data=owned)

    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=[]) as fetched, \
         patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", side_effect=_get):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_inbox(address="someone@trustxmail.com")

    assert exc_info.value.exit_code == 1
    out = capsys.readouterr().out
    assert "someone@trustxmail.com is not one of this account's email addresses" in out
    assert "aaron@mail.openonion.ai" in out
    assert "aaron.xie@mail.openonion.ai" in out
    assert "no emails" not in out
    fetched.assert_called_once()


def test_empty_inbox_accepts_an_owned_address_in_any_case(capsys):
    owned = {"addresses": [{"address": "aaron@mail.openonion.ai"}]}
    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=[]), \
         patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", return_value=_resp(json_data=owned)):
        email_commands.handle_email_inbox(address="Aaron@Mail.Openonion.ai")
    assert "no emails at Aaron@Mail.Openonion.ai" in capsys.readouterr().out


def test_empty_inbox_for_a_readable_grant_is_still_an_empty_mailbox(capsys):
    owned = {"addresses": [{"address": "aaron@mail.openonion.ai"}]}
    granted = [{"address": "leads@mail.openonion.ai", "can_send": False, "can_read": True}]

    def _get(url, **kwargs):
        if str(url).endswith("/api/v1/email/share"):
            return _resp(json_data={"granted_by_me": [], "granted_to_me": granted})
        return _resp(json_data=owned)

    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=[]), \
         patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", side_effect=_get):
        email_commands.handle_email_inbox(address="Leads@mail.openonion.ai")
    out = capsys.readouterr().out
    assert "no emails at Leads@mail.openonion.ai" in out
    assert "not one of this account's email addresses" not in out


def test_a_send_only_grant_is_not_an_inbox_address(capsys):
    owned = {"addresses": [{"address": "aaron@mail.openonion.ai"}]}
    granted = [{"address": "leads@mail.openonion.ai", "can_send": True, "can_read": False}]

    def _get(url, **kwargs):
        if str(url).endswith("/api/v1/email/share"):
            return _resp(json_data={"granted_to_me": granted})
        return _resp(json_data=owned)

    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=[]), \
         patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", side_effect=_get):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_inbox(address="leads@mail.openonion.ai")
    assert exc_info.value.exit_code == 1
    out = capsys.readouterr().out
    assert "leads@mail.openonion.ai is not one of this account's email addresses" in out
    assert "Yours are: aaron@mail.openonion.ai" in out
    assert "no emails" not in out


def test_an_account_with_no_addresses_is_told_the_list_is_empty(capsys):
    def _get(url, **kwargs):
        if str(url).endswith("/api/v1/email/share"):
            return _resp(json_data={"granted_to_me": []})
        return _resp(json_data={"addresses": []})

    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=[]), \
         patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", side_effect=_get):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_inbox(address="someone@trustxmail.com")
    assert exc_info.value.exit_code == 1
    assert "Yours are: (none)" in capsys.readouterr().out


def test_unread_filter_of_a_real_page_is_not_an_ownership_error(capsys):
    page = [dict(ONE_MAILBOX[0], read=True)]
    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=page), \
         patch.object(email_commands.requests, "get") as get:
        email_commands.handle_email_inbox(address="someone@trustxmail.com", unread=True)
    out = capsys.readouterr().out
    assert "no unread emails at someone@trustxmail.com" in out
    assert "not one of this account's email addresses" not in out
    get.assert_not_called()


def test_address_list_failure_is_not_reported_as_an_empty_inbox(capsys):
    failed = _resp(ok=False, status=500, json_data={"detail": "boom"})
    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=[]), \
         patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", return_value=failed):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_inbox(address="aaron@mail.openonion.ai")
    assert exc_info.value.exit_code == 1
    out = capsys.readouterr().out
    assert "boom" in out
    assert "no emails" not in out


def test_share_lookup_failure_is_not_reported_as_an_empty_inbox(capsys):
    owned = {"addresses": [{"address": "aaron@mail.openonion.ai"}]}

    def _get(url, **kwargs):
        if str(url).endswith("/api/v1/email/share"):
            return _resp(ok=False, status=503, json_data={"detail": "share down"})
        return _resp(json_data=owned)

    with patch.object(email_commands, "_require_auth", return_value=True), \
         patch.object(get_emails_module, "get_emails", return_value=[]), \
         patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "get", side_effect=_get):
        with pytest.raises(typer.Exit) as exc_info:
            email_commands.handle_email_inbox(address="leads@mail.openonion.ai")
    assert exc_info.value.exit_code == 1
    out = capsys.readouterr().out
    assert "share down" in out
    assert "no emails" not in out
    assert "not one of this account's email addresses" not in out


def test_get_emails_refuses_a_backend_that_ignored_the_filter():
    """An old backend answers with every address; degrading silently is the bug."""
    unfiltered = {"emails": [], "offset": 0, "address_filter_applied": None}
    with patch.object(get_emails_module, "require_ambient_api_key", return_value="tok"), \
         patch.object(get_emails_module.requests, "get", return_value=_resp(json_data=unfiltered)):
        with pytest.raises(RuntimeError, match="does not support filtering received email by address"):
            get_emails_module.get_emails(address="aaron@mail.openonion.ai")


def test_get_emails_sends_the_address_param_and_returns_to():
    body = {
        "emails": [{"id": 1, "from": "a@b.c", "to": "aaron@mail.openonion.ai",
                    "subject": "s", "text": "t", "received_at": "x", "is_read": False}],
        "offset": 0,
        "address_filter_applied": "aaron@mail.openonion.ai",
    }
    with patch.object(get_emails_module, "require_ambient_api_key", return_value="tok"), \
         patch.object(get_emails_module.requests, "get", return_value=_resp(json_data=body)) as get:
        emails = get_emails_module.get_emails(address="aaron@mail.openonion.ai")
    assert get.call_args.kwargs["params"]["address"] == "aaron@mail.openonion.ai"
    assert emails[0]["to"] == "aaron@mail.openonion.ai"


def test_default_sender_can_be_changed(capsys):
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "post", return_value=_resp(json_data={"success": True})) as post:
        email_commands.handle_email_default("aaron@mail.openonion.ai")
    assert post.call_args.kwargs["json"] == {"address": "aaron@mail.openonion.ai"}
    assert "default sender" in capsys.readouterr().out


def test_default_sender_failure_exits_nonzero(capsys):
    refusal = _resp(ok=False, status=403, json_data={"detail": "not one of this account's own addresses"})
    with patch.object(email_commands, "load_api_key", return_value="tok"), \
         patch.object(email_commands.requests, "post", return_value=refusal):
        with pytest.raises(typer.Exit):
            email_commands.handle_email_default("someone.else@mail.openonion.ai")
