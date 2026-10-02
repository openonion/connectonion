"""Feedback collection is scoped, durable, read-only, and restartable."""

import hashlib
import json
from importlib import import_module
from urllib.parse import parse_qs, urlparse

import pytest

from connectonion.cli.commands import feedback_commands as feedback

mail_module = import_module("connectonion.useful_tools.get_emails")


def message(identifier, subject=feedback.SUBJECT, to=feedback.EMAIL):
    return {
        "id": str(identifier),
        "to": to,
        "from": "user@example.com",
        "subject": subject,
        "message": "Problem description",
        "read": False,
    }


def test_collect_paginates_filters_and_restart_deduplicates(tmp_path, monkeypatch):
    rows = [message(n) for n in range(105, 0, -1)]
    rows[1] = message(104, subject="Private unrelated mail")
    rows[2] = message(103, to="someone-else@example.com")
    calls = []

    def get_emails(**kwargs):
        calls.append(kwargs)
        offset = kwargs.get("offset", 0)
        return rows[offset : offset + kwargs["last"]]

    monkeypatch.setattr(mail_module, "get_emails", get_emails)
    assert feedback.collect(tmp_path) == 103
    assert [call["offset"] for call in calls] == [0, 100]
    assert all(call["address"] == feedback.EMAIL and "unread" not in call for call in calls)
    receipts = [p for p in tmp_path.glob("*.json") if p.name != "cursor.json"]
    assert len(receipts) == 103
    assert all(json.loads(p.read_text())["read"] is False for p in receipts)
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in receipts)
    assert json.loads((tmp_path / "cursor.json").read_text()) == {"newest": "105"}
    assert feedback.collect(tmp_path) == 0
    rows.insert(0, message(106))
    assert feedback.collect(tmp_path) == 1


def test_crash_before_cursor_update_can_be_replayed(tmp_path, monkeypatch):
    monkeypatch.setattr(mail_module, "get_emails", lambda **kwargs: [message(1)])
    original = feedback.finish_collection

    def fail(*args):
        raise RuntimeError("interrupted before cursor")

    monkeypatch.setattr(feedback, "finish_collection", fail)
    with pytest.raises(RuntimeError):
        feedback.collect(tmp_path)
    assert not (tmp_path / "cursor.json").exists()
    monkeypatch.setattr(feedback, "finish_collection", original)
    assert feedback.collect(tmp_path) == 0
    assert json.loads((tmp_path / "cursor.json").read_text())["newest"] == "1"


def test_partial_temporary_receipt_is_replaced_before_advancing(tmp_path, monkeypatch):
    temporary = tmp_path / (hashlib.sha256(b"1").hexdigest() + ".tmp")
    temporary.write_text('{"id":')
    monkeypatch.setattr(mail_module, "get_emails", lambda **kwargs: [message(1)])
    assert feedback.collect(tmp_path) == 1
    assert not temporary.exists()
    assert json.loads(temporary.with_suffix(".json").read_text())["id"] == "1"


def test_read_failure_does_not_advance_cursor(tmp_path, monkeypatch):
    def fail(**kwargs):
        raise ValueError("backend refused scoped mailbox read")

    monkeypatch.setattr(mail_module, "get_emails", fail)
    with pytest.raises(ValueError):
        feedback.collect(tmp_path)
    assert not (tmp_path / "cursor.json").exists()


def test_report_has_prefilled_context_and_approved_email():
    links = feedback.channels("co gsheets read")
    assert links["email"] == "aaron.xie@mail.openonion.ai"
    assert links["discord"] == "https://discord.gg/4xfD9k8AUF"
    assert parse_qs(urlparse(links["mailto"]).query)["subject"] == [feedback.SUBJECT]
    body = parse_qs(urlparse(links["issue"]).query)["body"][0]
    assert "co gsheets read" in body and "co version:" in body


@pytest.mark.parametrize("error", [None, ValueError("unexpected failure")])
def test_cli_finally_includes_feedback_once_on_success_or_error(error, monkeypatch, capsys):
    from connectonion.cli import main

    def command():
        if error:
            raise error
        print('{"raw":true}')

    monkeypatch.setattr(main, "app", command)
    if error:
        with pytest.raises(ValueError):
            main.cli()
    else:
        main.cli()
    captured = capsys.readouterr()
    assert captured.err.count("Feedback:") == 1
    assert feedback.EMAIL in captured.err
    assert "Feedback:" not in captured.out
    if not error:
        assert json.loads(captured.out) == {"raw": True}


def test_subjectless_mail_does_not_stop_the_listener(tmp_path, monkeypatch):
    monkeypatch.setattr(mail_module, "get_emails", lambda **kwargs: [message(2, subject=None), message(1)])
    assert feedback.collect(tmp_path) == 1


def test_http_error_prints_channels_without_dumping_url(monkeypatch, capsys):
    import httpx

    from connectonion.cli import main

    def command():
        raise httpx.ConnectError("https://example.test?token=private")

    monkeypatch.setattr(main, "app", command)
    with pytest.raises(SystemExit) as error:
        main.cli()
    captured = capsys.readouterr()
    assert error.value.code == 1
    assert captured.out == ""
    assert "API connection failed" in captured.err and feedback.EMAIL in captured.err
    assert "private" not in captured.err and captured.err.count("Feedback:") == 1
