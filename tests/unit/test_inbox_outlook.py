"""The Outlook inbox provider (#1733) against a fake Graph delta: pages, the saved
delta link, crash safety, the 410 restart, the sender filter and a refused grant."""

import json

import pytest

from connectonion.inbox import ListenerStopped
from connectonion.inbox.outlook import Outlook, _State
from connectonion.inbox.store import Inbox


def mail(i, sender="z55{:05d}@student.unsw.edu.au", received="2026-10-13T10:{:02d}:00Z"):
    return {"id": f"m{i}", "conversationId": f"c{i}", "subject": f"Team {i}", "bodyPreview": "hello",
            "from": f"Student {i} <{sender.format(i)}>", "receivedDateTime": received.format(i)}


class FakeTool:
    def __init__(self, fn):
        self.fn = fn
        self.calls = []

    async def ainvoke(self, args):
        self.calls.append(args)
        return self.fn(args)


class FakeGraph:
    """messages_delta over a folder: a first round in pages, then whatever was added."""

    def __init__(self, pages, after=None):
        self.pages = pages          # first round: list of lists
        self.after = after or {}    # delta link -> list of messages
        self.fail = None
        self.messages_delta = FakeTool(self._delta)
        self.mail_folders_get = FakeTool(lambda args: {"id": args["folder_id"]})

    def _delta(self, args):
        if self.fail:
            raise self.fail
        link = args.get("next_link")
        if link and link.startswith("page:"):
            index = int(link[5:])
        elif link:
            return {"value": self.after.get(link, []), "delta_link": link + "+"}
        else:
            index = 0
        page = {"value": self.pages[index]}
        if index + 1 < len(self.pages):
            page["next_link"] = f"page:{index + 1}"
        else:
            page["delta_link"] = "delta:1"
        return page


@pytest.fixture
def inbox(tmp_path):
    return Inbox("outlook", home=tmp_path)


def listener(monkeypatch, graph, **env):
    for key in ("CO_OUTLOOK_FROM", "CO_OUTLOOK_FOLDERS", "CO_OUTLOOK_SINCE"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    p = Outlook(credentials=object())
    monkeypatch.setattr(p, "_tools", lambda: graph)
    return p


def test_every_page_of_a_round_is_delivered_and_the_link_saved_after(monkeypatch, inbox):
    graph = FakeGraph([[mail(1), mail(2)], [mail(3)], [mail(4)]])
    p = listener(monkeypatch, graph, CO_OUTLOOK_FOLDERS="inbox")
    state = _State(inbox.root / "outlook-delta.json")
    p._round(inbox, state, "inbox", raw=False)
    assert [m.id for m in inbox.list_messages()] == ["m1", "m2", "m3", "m4"]
    assert json.loads((inbox.root / "outlook-delta.json").read_text())["inbox"]["delta_link"] == "delta:1"
    # The first call asks for created mail since a point, a page at a time, never $top.
    first = graph.messages_delta.calls[0]
    assert first["change_type"] == "created" and first["filter"].startswith("receivedDateTime ge ")
    assert "top" not in first


def test_the_next_round_follows_the_saved_link_and_delivers_only_what_is_new(monkeypatch, inbox):
    graph = FakeGraph([[mail(1)]], after={"delta:1": [mail(1), mail(2)]})
    p = listener(monkeypatch, graph, CO_OUTLOOK_FOLDERS="inbox")
    p._round(inbox, _State(inbox.root / "outlook-delta.json"), "inbox", raw=False)
    # A restart: fresh state object, same directory.
    p._round(inbox, _State(inbox.root / "outlook-delta.json"), "inbox", raw=False)
    assert graph.messages_delta.calls[-1]["next_link"] == "delta:1"
    assert [m.id for m in inbox.list_messages()] == ["m1", "m2"]  # m1 redelivered by Graph, dropped by the inbox


def test_a_crash_mid_round_repeats_the_round_rather_than_skipping_it(monkeypatch, inbox):
    graph = FakeGraph([[mail(1)], [mail(2)]])
    p = listener(monkeypatch, graph, CO_OUTLOOK_FOLDERS="inbox")
    calls = {"n": 0}
    original = graph._delta

    def dies_on_second_page(args):
        calls["n"] += 1
        if calls["n"] == 2:
            raise TimeoutError("read timeout")
        return original(args)

    graph.messages_delta.fn = dies_on_second_page
    with pytest.raises(TimeoutError):
        p._round(inbox, _State(inbox.root / "outlook-delta.json"), "inbox", raw=False)
    assert not (inbox.root / "outlook-delta.json").exists()  # nothing saved, so nothing skipped
    graph.messages_delta.fn = original
    p._round(inbox, _State(inbox.root / "outlook-delta.json"), "inbox", raw=False)
    assert [m.id for m in inbox.list_messages()] == ["m1", "m2"]


def test_a_410_restarts_from_the_last_delivered_message_not_from_now(monkeypatch, inbox):
    from charter.types.errors import APIError

    graph = FakeGraph([[mail(1), mail(2)]])
    p = listener(monkeypatch, graph, CO_OUTLOOK_FOLDERS="inbox")
    p._round(inbox, _State(inbox.root / "outlook-delta.json"), "inbox", raw=False)
    original = graph._delta

    def gone_once(args):
        if args.get("next_link") == "delta:1":
            raise APIError("syncStateNotFound", status_code=410)
        return original(args)

    graph.messages_delta.fn = gone_once
    p._round(inbox, _State(inbox.root / "outlook-delta.json"), "inbox", raw=False)
    assert graph.messages_delta.calls[-1]["filter"] == "receivedDateTime ge 2026-10-13T10:02:00Z"


def test_only_matching_senders_reach_the_inbox(monkeypatch, inbox):
    graph = FakeGraph([[mail(1), mail(2, sender="noreply@github.com"), mail(3)]])
    p = listener(monkeypatch, graph, CO_OUTLOOK_FOLDERS="inbox", CO_OUTLOOK_FROM="*@student.unsw.edu.au")
    p._round(inbox, _State(inbox.root / "outlook-delta.json"), "inbox", raw=False)
    assert [m.sender for m in inbox.list_messages()] == ["z5500001@student.unsw.edu.au", "z5500003@student.unsw.edu.au"]


def test_a_refused_grant_stops_the_listener_loudly(monkeypatch, inbox):
    from charter.types.errors import CredentialError

    graph = FakeGraph([[mail(1)]])
    graph.fail = CredentialError("invalid_grant")
    p = listener(monkeypatch, graph, CO_OUTLOOK_FOLDERS="inbox")
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(ListenerStopped, match="co auth microsoft"):
        p.run(inbox)


def test_a_timeout_is_logged_and_retried(monkeypatch, inbox):
    graph = FakeGraph([[mail(1)]])
    p = listener(monkeypatch, graph, CO_OUTLOOK_FOLDERS="inbox")
    graph.fail = TimeoutError("read timeout")
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
    assert "poll failed (TimeoutError" in (inbox.root / "log").read_text()
    assert [m.id for m in inbox.list_messages()] == ["m1"]
