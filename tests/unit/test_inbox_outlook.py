"""The Outlook inbox provider (#1733) against a fake Graph delta behind the real Outlook
tool: pages, the saved delta link, crash safety, the 410 restart, the sender filter,
a refused grant, a timeout, and replies."""

import json

import httpx
import pytest

from connectonion.inbox import ListenerStopped
from connectonion.inbox.outlook import Outlook, _State
from connectonion.inbox.store import Inbox

DELTA = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta"


def mail(i, sender="z55{:05d}@student.unsw.edu.au", received="2026-10-13T10:{:02d}:00Z"):
    return {"id": f"m{i}", "conversationId": f"c{i}", "subject": f"Team {i}", "bodyPreview": "hello",
            "uniqueBody": {"contentType": "text", "content": "When is the demo?"},
            "from": {"emailAddress": {"name": f"Student {i}", "address": sender.format(i)}},
            "receivedDateTime": received.format(i)}


class FakeGraph:
    """Graph's delta over one folder: a first round in pages, then whatever was added.
    `fail` is an exception to raise or a status to answer with."""

    def __init__(self, pages, after=None):
        self.pages = pages          # first round: list of lists
        self.after = after or {}    # delta token -> messages added since
        self.fail = None
        self.calls = []

    def request(self, method, url, headers=None, params=None, **kwargs):
        self.calls.append({"method": method, "url": url, "params": params, "headers": headers, **kwargs})
        if isinstance(self.fail, Exception):
            raise self.fail
        if isinstance(self.fail, int):
            return httpx.Response(self.fail, json={"error": {"code": "refused"}})
        if method == "POST":
            return httpx.Response(202)
        if url == DELTA:
            index = 0
        elif "$skiptoken=" in url:
            index = int(url.rsplit("=", 1)[1])
        else:
            token = url.rsplit("=", 1)[1]
            return httpx.Response(200, json={"value": self.after.get(token, []),
                                             "@odata.deltaLink": f"{DELTA}?$deltatoken={token}+"})
        page = {"value": self.pages[index]}
        if index + 1 < len(self.pages):
            page["@odata.nextLink"] = f"{DELTA}?$skiptoken={index + 1}"
        else:
            page["@odata.deltaLink"] = f"{DELTA}?$deltatoken=1"
        return httpx.Response(200, json=page)


@pytest.fixture
def inbox(tmp_path):
    return Inbox("outlook", home=tmp_path)


def listener(monkeypatch, graph, **env):
    for key in ("CO_OUTLOOK_FROM", "CO_OUTLOOK_FOLDERS", "CO_OUTLOOK_SINCE",
                "MICROSOFT_REFRESH_TOKEN", "MICROSOFT_TOKEN_EXPIRES_AT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MICROSOFT_SCOPES", "Mail.Read Mail.Send")
    monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "test-token")
    monkeypatch.setenv("CO_OUTLOOK_FOLDERS", "inbox")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", graph.request)
    return Outlook()


def state(inbox):
    return _State(inbox.root / "outlook-delta.json")


def test_every_page_of_a_round_is_delivered_and_the_link_saved_after(monkeypatch, inbox):
    graph = FakeGraph([[mail(1), mail(2)], [mail(3)], [mail(4)]])
    p = listener(monkeypatch, graph)
    p._round(inbox, state(inbox), "inbox", raw=False)
    assert [m.id for m in inbox.list_messages()] == ["m1", "m2", "m3", "m4"]
    assert inbox.list_messages()[0].text == "Team 1\n\nWhen is the demo?"
    saved = json.loads((inbox.root / "outlook-delta.json").read_text())
    assert saved["inbox"]["delta_link"] == f"{DELTA}?$deltatoken=1"
    # The first call asks for created mail since a point, a page at a time
    # through Prefer (never $top, which ends the round), with text bodies.
    first = graph.calls[0]
    assert first["params"]["changeType"] == "created"
    assert first["params"]["$filter"].startswith("receivedDateTime ge ")
    assert "$top" not in first["params"]
    assert first["headers"]["Prefer"] == 'odata.maxpagesize=50, outlook.body-content-type="text"'
    assert first["headers"]["Authorization"] == "Bearer test-token"


def test_the_next_round_follows_the_saved_link_and_delivers_only_what_is_new(monkeypatch, inbox):
    graph = FakeGraph([[mail(1)]], after={"1": [mail(1), mail(2)]})
    p = listener(monkeypatch, graph)
    p._round(inbox, state(inbox), "inbox", raw=False)
    # A restart: fresh state object, same directory.
    p._round(inbox, state(inbox), "inbox", raw=False)
    assert graph.calls[-1]["url"] == f"{DELTA}?$deltatoken=1"
    assert [m.id for m in inbox.list_messages()] == ["m1", "m2"]  # m1 redelivered by Graph, dropped by the inbox


def test_a_crash_mid_round_repeats_the_round_rather_than_skipping_it(monkeypatch, inbox):
    graph = FakeGraph([[mail(1)], [mail(2)]])
    p = listener(monkeypatch, graph)
    answer = graph.request

    def dies_on_second_page(method, url, **kwargs):
        if "$skiptoken=" in url:
            raise httpx.ReadTimeout("read timeout")
        return answer(method, url, **kwargs)

    monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", dies_on_second_page)
    with pytest.raises(httpx.ReadTimeout):
        p._round(inbox, state(inbox), "inbox", raw=False)
    assert not (inbox.root / "outlook-delta.json").exists()  # nothing saved, so nothing skipped
    monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", answer)
    p._round(inbox, state(inbox), "inbox", raw=False)
    assert [m.id for m in inbox.list_messages()] == ["m1", "m2"]


def test_a_410_restarts_from_the_last_delivered_message_not_from_now(monkeypatch, inbox):
    graph = FakeGraph([[mail(1), mail(2)]])
    p = listener(monkeypatch, graph)
    p._round(inbox, state(inbox), "inbox", raw=False)
    answer = graph.request

    def gone_once(method, url, **kwargs):
        if url.endswith("$deltatoken=1"):
            return httpx.Response(410, json={"error": {"code": "SyncStateNotFound"}})
        return answer(method, url, **kwargs)

    monkeypatch.setattr("connectonion.useful_tools.outlook.httpx.request", gone_once)
    p._round(inbox, state(inbox), "inbox", raw=False)
    assert graph.calls[-1]["params"]["$filter"] == "receivedDateTime ge 2026-10-13T10:02:00Z"


def test_only_matching_senders_reach_the_inbox(monkeypatch, inbox):
    graph = FakeGraph([[mail(1), mail(2, sender="noreply@github.com"), mail(3)]])
    p = listener(monkeypatch, graph, CO_OUTLOOK_FROM="*@student.unsw.edu.au")
    p._round(inbox, state(inbox), "inbox", raw=False)
    assert [m.sender for m in inbox.list_messages()] == ["z5500001@student.unsw.edu.au", "z5500003@student.unsw.edu.au"]


def test_a_refused_grant_stops_the_listener_loudly(monkeypatch, inbox):
    graph = FakeGraph([[mail(1)]])
    graph.fail = 401  # and no refresh token to try
    p = listener(monkeypatch, graph)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(ListenerStopped, match="co auth microsoft"):
        p.run(inbox)


def test_a_folder_graph_does_not_have_stops_the_listener_instead_of_polling_it(monkeypatch, inbox):
    graph = FakeGraph([[mail(1)]])
    graph.fail = 404
    p = listener(monkeypatch, graph)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(ListenerStopped, match="HTTP 404"):
        p.run(inbox)


def test_a_timeout_is_logged_and_retried(monkeypatch, inbox):
    graph = FakeGraph([[mail(1)]])
    p = listener(monkeypatch, graph)
    graph.fail = httpx.ReadTimeout("read timeout")
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 1:
            graph.fail = None          # the network comes back
        else:
            raise KeyboardInterrupt    # end the test after the good round

    monkeypatch.setattr("time.sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        p.run(inbox)
    assert "poll failed (ReadTimeout" in (inbox.root / "log").read_text()
    assert [m.id for m in inbox.list_messages()] == ["m1"]


def test_a_damaged_state_file_raises_instead_of_starting_over(inbox):
    (inbox.root / "outlook-delta.json").write_text("{not json")
    with pytest.raises(ValueError):
        _State(inbox.root / "outlook-delta.json")


def test_check_reports_a_refused_grant_with_its_fix(monkeypatch):
    graph = FakeGraph([[mail(1)]])
    graph.fail = 401
    p = listener(monkeypatch, graph)
    assert p.check() == ["Microsoft authorization expired. Next: co auth microsoft"]


def test_send_replies_in_the_thread_and_refuses_a_new_email(monkeypatch):
    graph = FakeGraph([[mail(1)]])
    p = listener(monkeypatch, graph)
    assert p.send("c1", "Thursday at 10.", reply_to="m1") == ""
    assert graph.calls[-1]["url"].endswith("/me/messages/m1/reply")
    assert graph.calls[-1]["json"] == {"comment": "<p>Thursday at 10.</p>"}
    with pytest.raises(ValueError, match="reply_to"):
        p.send("c1", "Thursday at 10.")
