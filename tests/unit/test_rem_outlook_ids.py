"""REM's Outlook reads keep message IDs stable across folder moves."""
from unittest.mock import Mock

import pytest

from connectonion.useful_tools.outlook import Outlook


@pytest.mark.parametrize("method,args", [
    ("list_inbox", ()),
    ("get_sent_emails", ()),
    ("get_email_body", ("immutable-id",)),
    ("list_between", ("2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z")),
    ("list_with", ("person@example.com", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z")),
])
def test_rem_outlook_reads_request_immutable_ids(monkeypatch, method, args):
    client = Outlook.__new__(Outlook)
    monkeypatch.setattr(client, "_get_access_token", lambda: "fixture-token")
    request = Mock(return_value=Mock(status_code=200, json=lambda: {"value": []}))
    monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", request)
    getattr(client, method)(*args)
    assert request.call_args.kwargs["headers"]["Prefer"] == 'IdType="ImmutableId"'
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer fixture-token"


def test_rem_outlook_paging_keeps_immutable_preference(monkeypatch):
    client = Outlook.__new__(Outlook)
    monkeypatch.setattr(client, "_get_access_token", lambda: "fixture-token")
    request = Mock(side_effect=[
        Mock(status_code=200, json=lambda: {"@odata.nextLink": client.GRAPH_API_URL + "/me/messages?next=2"}),
        Mock(status_code=200, json=lambda: {"value": []}),
    ])
    monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", request)
    client.list_with("person@example.com", "2026-10-01", "2026-10-02")
    assert request.call_count == 2
    assert all(call.kwargs["headers"]["Prefer"] == 'IdType="ImmutableId"' for call in request.call_args_list)
