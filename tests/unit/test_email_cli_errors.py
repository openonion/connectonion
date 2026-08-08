"""The Sent CLI explains backend version skew instead of dumping a traceback."""

import importlib
from unittest.mock import MagicMock

import requests

from connectonion.cli.commands import email_commands

get_emails = importlib.import_module("connectonion.useful_tools.get_emails")
send_email = importlib.import_module("connectonion.useful_tools.send_email")


def _http_error(status):
    response = MagicMock(status_code=status)
    return requests.HTTPError(f"HTTP {status}", response=response)


def test_sent_list_explains_an_old_backend(monkeypatch, capsys):
    monkeypatch.setattr(email_commands, "_require_auth", lambda: True)
    monkeypatch.setattr(
        get_emails, "get_sent", lambda **kwargs: (_ for _ in ()).throw(_http_error(404))
    )

    email_commands.handle_email_sent(last=0)

    output = capsys.readouterr().out
    assert "not available on this backend yet" in output
    assert "oo-api Sent endpoint" in output
    assert "deployed before this command" in output


def test_sent_read_hides_transport_tracebacks(monkeypatch, capsys):
    monkeypatch.setattr(email_commands, "_require_auth", lambda: True)
    monkeypatch.setattr(
        get_emails,
        "get_sent",
        lambda **kwargs: (_ for _ in ()).throw(requests.ConnectionError("secret host detail")),
    )

    email_commands.handle_email_sent_read("7")

    output = capsys.readouterr().out
    assert "Could not reach the email service" in output
    assert "secret host detail" not in output


def test_send_does_not_call_a_non_retryable_key_safe(monkeypatch, capsys):
    monkeypatch.setattr(email_commands, "_require_auth", lambda: True)
    monkeypatch.setattr(send_email, "send_email", lambda *args, **kwargs: {
        "success": False,
        "error": "The provider retry window expired.",
        "request_id": "req-old",
        "idempotency_key": "send-old",
        "retryable": False,
    })

    email_commands.handle_email_send("to@example.com", "subject", "body")

    output = capsys.readouterr().out
    assert "provider retry window expired" in output
    assert "Request ID: req-old" in output
    assert "Safe retry key" not in output
    assert "--idempotency-key" not in output
