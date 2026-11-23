"""Exercise both CLI identities through the existing Cloud mailbox contract."""

import json
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from connectonion import address
from connectonion.cli.main import app
from connectonion.handoff import sealing
from connectonion.inbox import agent_messages


class Response:
    def __init__(self, body):
        self.body = body
        self.status_code = 200

    def json(self):
        return self.body

    def raise_for_status(self):
        return None


@pytest.fixture
def mailbox(tmp_path, monkeypatch):
    alice = address.generate()
    bob = address.generate()
    rows = []
    active = [alice]
    trusted = {alice["address"], bob["address"]}

    def request(self, method, url, *, headers, timeout, **kwargs):
        assert url.endswith("/api/v1/messages")
        identity = headers["Authorization"].removeprefix("Bearer ")
        if method == "POST":
            row = {
                "id": len(rows) + 1,
                "from_address": identity,
                "to_address": kwargs["json"]["to"],
                "body": kwargs["json"]["body"],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            rows.append(row)
            return Response({"id": row["id"]})
        params = kwargs["params"]
        waiting = [row for row in rows if row["to_address"] == identity and row["id"] > params["after"]]
        return Response({"messages": waiting[:params["limit"]]})

    monkeypatch.setattr(agent_messages, "project_co_dir", lambda: tmp_path)
    monkeypatch.setattr(agent_messages, "project_identity", lambda _: active[0])
    monkeypatch.setattr(agent_messages, "signed_agent_token", lambda keys, _url: keys["address"])
    monkeypatch.setattr(agent_messages, "get_level", lambda sender, _: "contact" if sender in trusted else "stranger")
    monkeypatch.setattr(agent_messages, "is_admin", lambda *_: False)
    monkeypatch.setattr("requests.Session.request", request)
    return alice, bob, rows, active, trusted


def invoke(*args):
    return CliRunner().invoke(app, ["agent", *args])


def test_offline_message_is_sealed_listed_once_and_replied_to(mailbox):
    alice, bob, rows, active, _ = mailbox
    sent = invoke("send", bob["address"], "报告好了")
    assert sent.exit_code == 0, sent.output
    assert "Cloud accepted" in sent.output
    assert "报告好了" not in rows[0]["body"]
    active[0] = bob
    assert json.loads(invoke("ls", "--json").stdout) == []
    for _ in range(2):
        result = invoke("listen", "--once")
        assert result.exit_code == 0, result.output
    received, = json.loads(invoke("ls", "--json").stdout)
    assert received["text"] == "报告好了"
    assert received["sender"] == alice["address"]

    result = invoke("reply", received["id"], "收到")
    assert result.exit_code == 0, result.output
    assert json.loads(invoke("ls", "--json").stdout) == []
    active[0] = alice
    assert invoke("listen", "--once").exit_code == 0
    reply, = json.loads(invoke("ls", "--json").stdout)
    assert reply["text"] == "收到"
    assert reply["quoted"]["id"] == received["id"]


def test_listener_ignores_untrusted_malformed_and_handoff_rows(mailbox):
    alice, bob, rows, active, trusted = mailbox
    assert invoke("send", bob["address"], "untrusted").exit_code == 0
    trusted.remove(alice["address"])
    active[0] = bob
    assert invoke("listen", "--once").exit_code == 0
    assert json.loads(invoke("ls", "--json").stdout) == []

    trusted.add(alice["address"])
    rows[0]["body"] = json.dumps({"type": agent_messages.NOTE_TYPE, "sealed": "corrupt"})
    rows.append({**rows[0], "id": 2, "body": json.dumps({"subject": "[co handoff]", "message": "task"})})
    active[0] = alice
    assert invoke("send", bob["address"], "valid").exit_code == 0
    active[0] = bob
    assert invoke("listen", "--once").exit_code == 0
    received, = json.loads(invoke("ls", "--json").stdout)
    assert received["text"] == "valid"


def test_reply_cannot_use_another_local_identity_or_a_blocked_contact(mailbox):
    alice, bob, rows, active, trusted = mailbox
    assert invoke("send", bob["address"], "hello").exit_code == 0
    active[0] = bob
    assert invoke("listen", "--once").exit_code == 0
    message, = json.loads(invoke("ls", "--json").stdout)
    active[0] = alice
    assert invoke("reply", message["id"], "wrong identity").exit_code == 1
    active[0] = bob
    trusted.remove(alice["address"])
    assert invoke("reply", message["id"], "no longer trusted").exit_code == 1
    assert len(rows) == 1


def test_inner_message_type_is_bound_to_the_ciphertext(mailbox):
    alice, bob, rows, active, _ = mailbox
    assert invoke("send", bob["address"], "placeholder").exit_code == 0
    rows[0]["body"] = json.dumps({"type": agent_messages.NOTE_TYPE, "sealed": sealing.box(
        alice["signing_key"], bob["address"], {"type": "other", "text": "wrong protocol"})})
    active[0] = bob
    assert invoke("listen", "--once").exit_code == 0
    assert json.loads(invoke("ls", "--json").stdout) == []


def test_disconnected_poll_reports_failure_and_keeps_pending_messages(mailbox, monkeypatch):
    import requests

    alice, bob, _, active, _ = mailbox
    assert invoke("send", bob["address"], "first").exit_code == 0
    active[0] = bob
    assert invoke("listen", "--once").exit_code == 0

    def unavailable(*args, **kwargs):
        raise requests.ConnectionError("test mailbox offline")

    monkeypatch.setattr("requests.Session.request", unavailable)
    failed = invoke("listen", "--once")
    assert failed.exit_code == 1
    assert "Listening failed" in failed.output
    pending, = json.loads(invoke("ls", "--json").stdout)
    assert pending["text"] == "first"
    assert pending["sender"] == alice["address"]


def test_listener_drains_beyond_the_first_page(mailbox, monkeypatch):
    _, bob, _, active, _ = mailbox
    monkeypatch.setattr(agent_messages, "PAGE_SIZE", 1)
    for text in ("first", "second"):
        assert invoke("send", bob["address"], text).exit_code == 0
    active[0] = bob
    assert invoke("listen", "--once").exit_code == 0
    assert [row["text"] for row in json.loads(invoke("ls", "--json").stdout)] == ["first", "second"]
