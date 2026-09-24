"""One person's mail, asked of the server directly: complete, paged, inside the window."""

from connectonion.useful_tools.gmail import Gmail
from connectonion.useful_tools.outlook import Outlook


def graph_message(i, when, sender="vern.chan@unsw.edu.au", to=("me@outlook.com",)):
    return {"id": f"o{i}", "from": {"emailAddress": {"address": sender, "name": "Vern Chan"}},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to], "ccRecipients": [],
            "subject": f"s{i}", "receivedDateTime": when, "bodyPreview": "", "isRead": True}


def test_outlook_asks_for_the_participant_and_follows_every_page():
    outlook = Outlook.__new__(Outlook)
    calls = []
    pages = [
        {"value": [graph_message(2, "2026-07-21T00:00:00Z"), graph_message(1, "2026-07-10T00:00:00Z")],
         "@odata.nextLink": Outlook.GRAPH_API_URL + "/me/messages?$skiptoken=abc"},
        {"value": [graph_message(3, "2026-09-30T00:00:00Z"),             # after the window
                   graph_message(4, "2026-06-26T00:00:00Z", sender="me@outlook.com",
                                 to=("vern.chan@unsw.edu.au",))]},
    ]

    def request(method, endpoint, **kwargs):
        calls.append((endpoint, kwargs.get("params")))
        return pages[len(calls) - 1]

    outlook._request = request
    rows = outlook.list_with("vern.chan@unsw.edu.au", "2026-06-25T00:00:00+00:00", "2026-09-23T00:00:00+00:00")
    assert [r["id"] for r in rows] == ["o4", "o1", "o2"]                    # oldest first, window applied
    assert "participants:vern.chan@unsw.edu.au AND received>=2026-06-25" in calls[0][1]["$search"]
    assert calls[1] == ("/me/messages?$skiptoken=abc", None)                 # the second page was followed
    assert rows[0]["to"] == ["vern.chan@unsw.edu.au"]                       # recipients, so sent mail files right


class FakeGmailService:
    def __init__(self, pages, headers):
        self.pages, self.headers, self.queries = pages, headers, []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, q, maxResults, pageToken=None):
        self.queries.append((q, pageToken))
        page = self.pages[len(self.queries) - 1]
        return type("Call", (), {"execute": lambda _self: page})()

    def get(self, userId, id, format, metadataHeaders):
        headers = [{"name": k, "value": v} for k, v in self.headers[id].items()]
        return type("Call", (), {"execute": lambda _self: {"payload": {"headers": headers}, "labelIds": []}})()


def test_gmail_searches_all_three_fields_and_follows_page_tokens():
    service = FakeGmailService(
        pages=[{"messages": [{"id": "g2"}], "nextPageToken": "t1"}, {"messages": [{"id": "g1"}]}],
        headers={"g1": {"From": "Ody <zhouodywork@gmail.com>", "To": "me@gmail.com", "Subject": "a",
                        "Date": "Mon, 07 Sep 2026 10:00:00 +1000"},
                 "g2": {"From": "me@gmail.com", "To": "zhouodywork@gmail.com", "Cc": "x@y.z", "Subject": "b",
                        "Date": "Tue, 08 Sep 2026 10:00:00 +1000"}})
    gmail = Gmail.__new__(Gmail)
    gmail._get_service = lambda: service
    rows = gmail.list_with("zhouodywork@gmail.com", "2026-06-25T00:00:00+00:00", "2026-09-23T00:00:00+00:00")
    assert [r["id"] for r in rows] == ["g1", "g2"]
    q, token = service.queries[0]
    assert q.startswith("{from:zhouodywork@gmail.com to:zhouodywork@gmail.com cc:zhouodywork@gmail.com}")
    assert "after:" in q and "before:" in q
    assert service.queries[1][1] == "t1"
    assert rows[1]["to"] == ["zhouodywork@gmail.com"] and rows[1]["cc"] == ["x@y.z"]


def test_outlook_waits_out_throttling_instead_of_failing(monkeypatch):
    """Several investigations reading one mailbox drew HTTP 429 and the run died
    on a request Graph would have answered a few seconds later."""
    import httpx
    import connectonion.useful_tools.outlook as module
    outlook = Outlook.__new__(Outlook)
    outlook._get_access_token = lambda: "token"
    replies = [httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json={"value": []})]
    monkeypatch.setattr(module.httpx, "request", lambda *a, **k: replies.pop(0))
    waited = []
    monkeypatch.setattr(module.time, "sleep", waited.append)
    assert outlook._request("GET", "/me/messages") == {"value": []}
    assert waited == [2.0]
