"""Unit tests for the mailbox directory behind `co <provider> listen`.

LLM-Note: Tests for connectonion.listen.mailbox

What it tests:
- A delivered message is one log line and one queue file; a duplicate id is neither
- receive() takes a message exactly once, even with two consumers, and times out cleanly
- Taken-but-unanswered messages come back; replied ones are forgotten
- The log survives a torn line, and reply lookups read it
- The listener lock ignores a dead pid and receive() starts a listener when none runs

Components under test:
- Module: connectonion/listen/mailbox.py
"""

import json
import os
import threading
import time

import pytest

from connectonion.listen import mailbox as mailbox_module
from connectonion.listen.mailbox import Mailbox, Message, default_home


def make(tmp_path):
    return Mailbox("feishu", home=tmp_path / "feishu")


def msg(i="om_1", chat="oc_a", text="hello", **kw):
    return Message(id=i, chat=chat, sender="on_x", text=text, at="2026-09-02T10:00:00Z", **kw)


def test_a_delivered_message_is_one_log_line_and_one_queue_file(tmp_path):
    box = make(tmp_path)

    assert box.deliver(msg()) is True

    lines = box.inbox.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == "hello"
    assert len(box.unread()) == 1
    assert box.unread()[0].name.endswith("-om_1")


def test_a_duplicate_id_is_dropped_even_after_a_restart(tmp_path):
    box = make(tmp_path)
    box.deliver(msg())

    fresh = make(tmp_path)  # a new process reads the log to know what it has seen
    assert fresh.deliver(msg(text="redelivered")) is False

    assert len(box.inbox.read_text().splitlines()) == 1
    assert len(box.unread()) == 1


def test_raw_payload_is_logged_only_when_asked_and_never_queued(tmp_path):
    box = make(tmp_path)
    box.deliver(msg(raw={"secret": "group title"}), raw=True)

    assert "group title" in box.inbox.read_text()
    assert "group title" not in box.unread()[0].read_text()

    box.deliver(msg(i="om_2", raw={"secret": "x"}))  # raw=False by default
    assert box.inbox.read_text().count("secret") == 1


def test_receive_takes_the_oldest_and_moves_it_to_cur(tmp_path):
    box = make(tmp_path)
    box.deliver(msg(i="om_first"))
    time.sleep(0.002)
    box.deliver(msg(i="om_second"))

    got = box.receive(timeout=0)

    assert got.id == "om_first"
    assert [p.name.split("-", 1)[1] for p in box.unread()] == ["om_second"]
    assert any(p.name.endswith("-om_first") for p in box.cur.iterdir())


def test_receive_with_no_message_returns_none_after_the_timeout(tmp_path):
    box = make(tmp_path)
    started = time.monotonic()

    assert box.receive(timeout=0.3, poll=0.05) is None
    assert time.monotonic() - started >= 0.3


def test_receive_wakes_when_a_message_arrives(tmp_path):
    box = make(tmp_path)
    result = {}

    def consumer():
        result["msg"] = box.receive(timeout=5, poll=0.02)

    thread = threading.Thread(target=consumer)
    thread.start()
    time.sleep(0.1)
    box.deliver(msg(i="om_late"))
    thread.join(timeout=5)

    assert result["msg"].id == "om_late"


def test_two_consumers_never_take_the_same_message(tmp_path):
    box = make(tmp_path)
    for i in range(40):
        box.deliver(msg(i=f"om_{i:02d}"))
    taken = []
    lock = threading.Lock()

    def consumer():
        while True:
            got = box.receive(timeout=0)
            if got is None:
                return
            with lock:
                taken.append(got.id)

    threads = [threading.Thread(target=consumer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(taken) == [f"om_{i:02d}" for i in range(40)]
    assert len(taken) == len(set(taken))


def test_a_taken_message_nobody_answered_comes_back_after_an_hour(tmp_path):
    box = make(tmp_path)
    box.deliver(msg())
    box.receive(timeout=0)
    (path,) = list(box.cur.iterdir())
    old = time.time() - 4000
    os.utime(path, (old, old))

    assert box.release_stale() == 1
    assert len(box.unread()) == 1
    assert box.receive(timeout=0).id == "om_1"


def test_done_forgets_a_taken_message(tmp_path):
    box = make(tmp_path)
    box.deliver(msg())
    box.receive(timeout=0)

    box.done("om_1")

    assert list(box.cur.iterdir()) == []


def test_lookup_finds_a_message_by_id_and_skips_a_torn_line(tmp_path):
    box = make(tmp_path)
    box.deliver(msg(i="om_a", chat="oc_1", thread="om_root"))
    with box.inbox.open("a") as handle:
        handle.write('{"id": "om_torn", "chat": "oc_')  # crashed mid-write

    found = box.lookup("om_a")

    assert found.chat == "oc_1"
    assert found.thread == "om_root"
    assert box.lookup("om_torn") is None
    assert box.lookup("om_missing") is None


def test_outbox_records_replies_so_a_second_reply_can_be_refused(tmp_path):
    box = make(tmp_path)

    box.record_sent(chat="oc_1", text="failed once", reply_to="om_a", error="rate limited")
    assert box.already_replied("om_a") is False

    box.record_sent(chat="oc_1", text="done", reply_to="om_a", provider_id="om_reply")
    assert box.already_replied("om_a") is True

    records = [json.loads(line) for line in box.outbox.read_text().splitlines()]
    assert [r["ok"] for r in records] == [False, True]


def test_the_lock_ignores_a_dead_pid(tmp_path):
    box = make(tmp_path)
    box.lock.write_text("999999999\n")

    assert box.listener_pid() is None
    assert box.hold_lock() is True
    assert box.listener_pid() == os.getpid()

    fresh = make(tmp_path)
    assert fresh.hold_lock() is False

    box.release_lock()
    assert box.listener_pid() is None


def test_ensure_listener_starts_one_only_when_none_is_running(tmp_path, monkeypatch):
    box = make(tmp_path)
    spawned = []

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None  # still running

    def fake_popen(argv, **kwargs):
        spawned.append(argv)
        return FakeProcess()

    monkeypatch.setattr(mailbox_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(mailbox_module.time, "sleep", lambda s: None)

    assert box.ensure_listener() == 4242
    assert spawned[0][-2:] == ["feishu", "listen"]
    assert "listener started pid 4242" in box.logfile.read_text()

    box.lock.write_text(f"{os.getpid()}\n")  # a live listener
    assert box.ensure_listener() == os.getpid()
    assert len(spawned) == 1


def test_default_home_is_under_dot_co_unless_overridden(monkeypatch, tmp_path):
    monkeypatch.delenv("CO_FEISHU_HOME", raising=False)
    assert default_home("feishu") == mailbox_module.Path.home() / ".co" / "feishu"

    monkeypatch.setenv("CO_FEISHU_HOME", str(tmp_path / "ops-bot"))
    assert default_home("feishu") == tmp_path / "ops-bot"


def test_message_json_has_the_same_seven_keys_in_order(tmp_path):
    record = json.loads(msg(thread=None, mentioned=False).to_json())

    assert list(record) == ["id", "chat", "thread", "sender", "text", "mentioned", "at"]
    assert Message.from_dict(record) == msg(thread=None, mentioned=False)


@pytest.mark.skipif(os.name != "posix", reason="mode bits are a posix thing")
def test_the_directory_is_private(tmp_path):
    box = make(tmp_path)
    assert oct(box.root.stat().st_mode & 0o777) == "0o700"


def test_a_listener_that_dies_at_once_is_reported_not_waited_for(tmp_path, monkeypatch):
    """No SDK, bad credentials: the child exits 3 within a second. receive()
    must not then wait forever for files that will never come."""
    box = make(tmp_path)

    class DeadProcess:
        pid = 4243
        returncode = 3

        def poll(self):
            return 3

    monkeypatch.setattr(mailbox_module.subprocess, "Popen", lambda argv, **kw: DeadProcess())
    monkeypatch.setattr(mailbox_module.time, "sleep", lambda s: None)

    assert box.ensure_listener() is None
    assert "listener exited at once with 3" in box.logfile.read_text()


def test_the_stale_clock_starts_at_the_claim_not_at_delivery(tmp_path):
    """A message delivered two hours ago and taken a minute ago is not stale.
    rename() keeps the old mtime, so the claim has to reset it, or the sweep
    hands the message out a second time while the first consumer is on it."""
    box = make(tmp_path)
    box.deliver(msg())
    (queued,) = box.unread()
    old = time.time() - 7200
    os.utime(queued, (old, old))

    box.receive(timeout=0)

    assert box.release_stale() == 0
    assert box.unread() == []
