"""REM Gmail listing uses the bounded direct transport and preserves source identity."""

from threading import Barrier
from urllib.parse import unquote

import pytest

from connectonion.useful_tools.gmail import Gmail


def client(monkeypatch, read):
    gmail = Gmail.__new__(Gmail)
    monkeypatch.setattr(gmail, "_mailbox_get", read)
    monkeypatch.setattr(gmail, "_get_service", lambda: pytest.fail("REM used the SDK transport"))
    return gmail


def test_rem_account_uses_provider_profile_and_send_as_aliases(monkeypatch):
    calls = []

    def read(path, **kwargs):
        calls.append(path)
        return ({"emailAddress": "Owner@Example.test"} if path == "profile" else
                {"sendAs": [{"sendAsEmail": "Alias@Example.test"}]})

    assert client(monkeypatch, read).my_addresses() == {"owner@example.test", "alias@example.test"}
    assert calls == ["profile", "settings/sendAs"]


def test_rem_full_window_defers_metadata_until_it_is_split(monkeypatch):
    calls = []

    def read(path, **kwargs):
        calls.append(path)
        return {"messages": [{"id": str(n)} for n in range(200)]}

    rows = client(monkeypatch, read).list_between_for_rem("2026-09-01T00:00:00+00:00",
                                                         "2026-09-08T00:00:00+00:00", 200)
    assert len(rows) == 200 and calls == ["messages"]


def test_rem_metadata_is_fetched_concurrently_but_sorted_by_message_date(monkeypatch):
    barrier = Barrier(2, timeout=2)
    calls = []

    def read(path, **kwargs):
        calls.append(path)
        if path == "messages":
            return {"messages": [{"id": "new", "threadId": "thread-new"},
                                 {"id": "old", "threadId": "thread-old"}]}
        assert kwargs['ensure_service'] is False
        assert kwargs['params']['format'] == 'metadata'
        barrier.wait()
        old = path.endswith("old")
        return {"id": unquote(path.split("/")[-1]), "snippet": "preview", "labelIds": [],
                "payload": {"headers": [
                    {"name": "From", "value": "Friend <friend@example.test>"},
                    {"name": "To", "value": "Owner <owner@example.test>"},
                    {"name": "Cc", "value": "Colleague <colleague@example.test>"},
                    {"name": "Date", "value": "Mon, 01 Sep 2025 00:00:00 +0000" if old
                     else "Tue, 02 Sep 2025 00:00:00 +0000"},
                    {"name": "Subject", "value": "Project"}]}}

    rows = client(monkeypatch, read).list_between_for_rem("2025-09-01T00:00:00+00:00",
                                                         "2025-09-08T00:00:00+00:00", 200)
    assert [row["id"] for row in rows] == ["old", "new"]
    assert rows[0]["thread_id"] == "thread-old"
    assert rows[0]["to"] == ["Owner <owner@example.test>"]
    assert rows[0]["cc"] == ["Colleague <colleague@example.test>"]
    assert len(calls) == 3


def test_rem_metadata_error_does_not_return_a_partial_success(monkeypatch):
    def read(path, **kwargs):
        if path == "messages":
            return {"messages": [{"id": "one"}, {"id": "two"}]}
        if path.endswith("two"):
            raise TimeoutError("provider timeout")
        return {"id": "one", "payload": {"headers": []}}

    with pytest.raises(TimeoutError):
        client(monkeypatch, read).list_between_for_rem("2026-09-01T00:00:00+00:00",
                                                     "2026-09-08T00:00:00+00:00", 200)
