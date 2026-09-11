"""Unit tests for the inbox directory behind `co <provider> listen`.

LLM-Note: Tests for connectonion.inbox.store

What it tests:
- A delivered message is one log line and one queue file; a duplicate id is neither
- receive() takes a message exactly once, even with two consumers, and times out cleanly
- Taken-but-unanswered messages come back; replied ones are forgotten
- The log survives a torn line, and reply lookups read it
- The listener lock ignores a dead pid and receive() starts a listener when none runs

Components under test:
- Module: connectonion/listen/inbox.py
"""

import json
import os
from pathlib import Path
import threading
import time

import pytest

from connectonion.inbox import store as store_module
from connectonion.inbox.store import Inbox, Message, default_home, inbox_root


def make(tmp_path):
    return Inbox("feishu", home=tmp_path / "feishu")


def msg(i="om_1", chat="oc_a", text="hello", **kw):
    return Message(id=i, chat=chat, sender="on_x", text=text, at="2026-09-02T10:00:00Z", **kw)


def test_a_delivered_message_is_one_log_line_and_one_queue_file(tmp_path):
    box = make(tmp_path)

    assert box.deliver(msg()) is True

    lines = box.received.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == "hello"
    assert len(box.unread()) == 1
    assert box.unread()[0].name.endswith("-om_1")


def test_a_duplicate_id_is_dropped_even_after_a_restart(tmp_path):
    box = make(tmp_path)
    box.deliver(msg())

    fresh = make(tmp_path)  # a new process reads the log to know what it has seen
    assert fresh.deliver(msg(text="redelivered")) is False

    assert len(box.received.read_text().splitlines()) == 1
    assert len(box.unread()) == 1


def test_raw_payload_is_logged_only_when_asked_and_never_queued(tmp_path):
    box = make(tmp_path)
    box.deliver(msg(raw={"secret": "group title"}), raw=True)

    assert "group title" in box.received.read_text()
    assert "group title" not in box.unread()[0].read_text()

    box.deliver(msg(i="om_2", raw={"secret": "x"}))  # raw=False by default
    assert box.received.read_text().count("secret") == 1


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
    with box.received.open("a") as handle:
        handle.write('{"id": "om_torn", "chat": "oc_')  # crashed mid-write

    found = box.lookup("om_a")

    assert found.chat == "oc_1"
    assert found.thread == "om_root"
    assert box.lookup("om_torn") is None
    assert box.lookup("om_missing") is None


def test_sent_log_records_replies_so_a_second_reply_can_be_refused(tmp_path):
    box = make(tmp_path)

    box.record_sent(chat="oc_1", text="failed once", reply_to="om_a", error="rate limited")
    assert box.already_replied("om_a") is False

    box.record_sent(chat="oc_1", text="done", reply_to="om_a", provider_id="om_reply")
    assert box.already_replied("om_a") is True

    records = [json.loads(line) for line in box.sent.read_text().splitlines()]
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
        box.lock.write_text("4242\n")  # what the child does once it is up
        return FakeProcess()

    monkeypatch.setattr(store_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(store_module, "_held", lambda path: True)  # whoever wrote the file holds it

    assert box.ensure_listener() == 4242
    assert spawned[0][-2:] == ["feishu", "listen"]
    assert "listener started pid 4242" in box.logfile.read_text()

    box.lock.write_text(f"{os.getpid()}\n")  # a live listener
    assert box.ensure_listener() == os.getpid()
    assert len(spawned) == 1


def test_default_home_is_under_dot_co_unless_overridden(monkeypatch, tmp_path):
    # One root for every channel: a consumer watches inbox/*/new/ rather than
    # a list of directories somebody has to keep in sync.
    monkeypatch.delenv("CO_INBOX_HOME", raising=False)
    assert default_home("feishu") == store_module.Path.home() / ".co" / "inbox" / "feishu"

    # The override moves the whole root, not one provider: moving one and
    # leaving the others only ever produced a half-configured machine.
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "ops-bot"))
    assert default_home("feishu") == tmp_path / "ops-bot" / "feishu"
    assert inbox_root() == tmp_path / "ops-bot"


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

    monkeypatch.setattr(store_module.subprocess, "Popen", lambda argv, **kw: DeadProcess())
    monkeypatch.setattr(store_module.time, "sleep", lambda s: None)

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


def test_two_receives_in_the_same_instant_get_one_listener(tmp_path, monkeypatch):
    """Parent B's child loses the lock race and exits; B must then report
    A's listener, not a failure."""
    box = make(tmp_path)

    class LostTheRace:
        pid = 5001
        returncode = 1

        def poll(self):
            box.lock.write_text("5000\n")  # A's child took the lock meanwhile
            return 1

    monkeypatch.setattr(store_module.subprocess, "Popen", lambda argv, **kw: LostTheRace())
    monkeypatch.setattr(store_module, "_held", lambda path: True)

    assert box.ensure_listener() == 5000


def test_the_lock_is_taken_exclusively(tmp_path):
    holder = make(tmp_path)
    assert holder.hold_lock() is True

    box = make(tmp_path)
    assert box.hold_lock() is False, "a live holder wins"
    assert box.lock.read_text().strip() == str(os.getpid())
    holder.release_lock()


def test_the_lock_is_held_by_the_kernel_not_by_the_pid_in_the_file(tmp_path):
    # Two defects with one root: the file was the lock. (a) O_EXCL created it
    # empty before the pid landed, so a second starter read "" and unlinked
    # the winner's lock: two listeners, every message delivered twice. (b)
    # After a reboot the pid in the file belongs to someone else, and nothing
    # ever cleared the phantom. An OS-held lock dies with its process.
    holder = make(tmp_path)
    assert holder.hold_lock() is True
    holder.lock.write_text("")  # the instant between create and write
    assert make(tmp_path).hold_lock() is False, "an empty lock file is a listener mid-start, not a dead one"
    assert holder.listener_pid() is None or holder.lock.read_text() == ""
    holder.release_lock()

    box = make(tmp_path)
    box.lock.write_text(f"{os.getpid()}\n")  # a live pid, but nobody holds the lock
    assert box.listener_pid() is None, "a pid in a file nobody holds is not a listener"
    assert box.hold_lock() is True
    assert box.listener_pid() == os.getpid()
    box.release_lock()
    assert box.listener_pid() is None


def test_a_redelivery_after_a_crash_between_log_and_queue_is_queued_not_dropped(tmp_path):
    # deliver() logs first, then queues. A crash between the two used to be
    # "recoverable from the log" in theory only: the redelivery Feishu sends
    # was refused as a duplicate because the id was already in the log.
    box = make(tmp_path)
    assert box.deliver(msg(i="om_c")) is True
    for path in box.new.iterdir():
        path.unlink()  # the queue file never made it

    assert box.deliver(msg(i="om_c")) is True, "the redelivery recreates the queue file"
    assert len(box.unread()) == 1
    assert sum(1 for _ in box._records(box.received)) == 1, "the log is not appended twice"

    assert box.deliver(msg(i="om_c")) is False, "queued: a duplicate"
    box.receive(0)
    assert box.deliver(msg(i="om_c")) is False, "taken: a duplicate"
    box.record_sent(chat="oc_a", text="ok", reply_to="om_c", provider_id="om_r")
    box.done("om_c")
    assert box.deliver(msg(i="om_c")) is False, "answered: a duplicate"


def test_junk_in_new_is_skipped_and_a_torn_queue_file_is_set_aside(tmp_path):
    # The directory is the interface, so Finder, editors and a disk-full crash
    # all leave files in it. None of them may crash every consumer.
    box = make(tmp_path)
    (box.new / ".DS_Store").write_bytes(b"\x00\x01")
    (box.new / "1-om_torn").write_text("")
    (box.new / "2-om_half").write_text('{"id":"om_half"}')
    box.deliver(msg(i="om_ok"))

    assert box.receive(0).id == "om_ok"
    assert box.receive(0) is None
    assert (box.new / ".DS_Store").exists(), "not ours; left alone"
    assert sorted(p.name for p in box.bad.iterdir()) == ["1-om_torn", "2-om_half"]
    assert "1-om_torn" in box.logfile.read_text()
    box.done("om_ok")
    assert box.release_stale(max_age=0) == 0, "nothing in bad/ is bounced back"


def test_lookup_skips_a_log_line_that_is_not_a_whole_message(tmp_path):
    box = make(tmp_path)
    box._append(box.received, '{"id":"om_z","text":"no chat"}')

    assert box.lookup("om_z") is None


def test_ensure_listener_pins_the_directory_and_forwards_the_env_file(tmp_path, monkeypatch):
    # The child is a fresh `co`, so it loads ~/.co/keys.env on its own. A
    # CO_INBOX_HOME there, or a --env-file the parent was started with, sent
    # the child to a different directory than the one waiting for it.
    box = make(tmp_path)
    seen = {}

    class Running:
        pid = 4321

        def poll(self):
            return None

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs.get("env")
        box.lock.write_text("4321\n")
        return Running()

    monkeypatch.setattr(store_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(store_module, "_held", lambda path: True)
    monkeypatch.setattr(store_module, "explicit_env_file", lambda: tmp_path / "app.env")

    assert box.ensure_listener() == 4321
    assert seen["env"]["CO_INBOX_HOME"] == str(box.root.parent)
    assert seen["argv"][3:5] == ["--env-file", str(tmp_path / "app.env")]
    assert seen["argv"][-2:] == ["feishu", "listen"]


def test_done_clears_the_queue_too_and_matches_the_whole_id(tmp_path):
    """A reply made from `ls` without a `receive` must not leave the message
    waiting; and Telegram's 123.55 must not delete -123.55."""
    box = make(tmp_path)
    box.deliver(msg(i="123.55"))
    box.deliver(msg(i="-123.55"))

    box.done("123.55")

    assert [p.name.split("-", 1)[1] for p in box.unread()] == ["-123.55"]


def test_done_without_a_reply_survives_redelivery_and_restart(tmp_path):
    box = make(tmp_path)
    box.deliver(msg())
    box.receive(0)
    box.done('om_1')
    assert make(tmp_path).deliver(msg()) is False
    assert box.receive(0) is None
    assert not box.already_replied('om_1'), 'choosing silence must not pretend a reply was sent'


def test_recovery_uses_the_original_logged_message(tmp_path):
    box = make(tmp_path)
    box.deliver(msg(chat='original', text='approved inbound'))
    box.unread()[0].unlink()
    box.deliver(msg(chat='different', text='changed payload'))
    received = box.receive(0)
    assert received.chat == 'original'
    assert received.text == 'approved inbound'


def test_torn_log_tail_does_not_swallow_the_next_message(tmp_path):
    box = make(tmp_path)
    box.received.write_text('{"id":"torn')
    box.deliver(msg())
    assert make(tmp_path).lookup('om_1').text == 'hello'


def test_releasing_listener_keeps_the_same_lock_inode(tmp_path):
    box = make(tmp_path)
    assert box.hold_lock()
    inode = box.lock.stat().st_ino
    box.release_lock()
    assert box.lock.exists(), 'unlinking a lock permits contenders to lock different inodes'
    assert box.lock.stat().st_ino == inode
    assert make(tmp_path).listener_pid() is None


def test_different_unsafe_ids_cannot_share_a_queue_file(tmp_path, monkeypatch):
    monkeypatch.setattr(store_module.time, 'time', lambda: 1)
    box = make(tmp_path)
    box.deliver(msg(i='unsafe/a'))
    box.deliver(msg(i='unsafe?a'))
    assert {box.receive(0).id, box.receive(0).id} == {'unsafe/a', 'unsafe?a'}


def test_sweep_cannot_reclaim_a_message_between_rename_and_claim_timestamp(tmp_path, monkeypatch):
    box = make(tmp_path)
    box.deliver(msg())
    old = time.time() - 7200
    os.utime(box.unread()[0], (old, old))
    renamed, continue_claim, swept = threading.Event(), threading.Event(), threading.Event()
    original_utime = os.utime
    result = {}

    def delayed_utime(path, *args, **kwargs):
        if Path(path).parent == box.cur:
            renamed.set()
            assert continue_claim.wait(5)
        return original_utime(path, *args, **kwargs)

    def sweep():
        result['released'] = make(tmp_path).release_stale()
        swept.set()

    monkeypatch.setattr(os, 'utime', delayed_utime)
    consumer = threading.Thread(target=lambda: result.update(message=box.receive(0)))
    reclaimer = threading.Thread(target=sweep)
    consumer.start()
    try:
        assert renamed.wait(5)
        reclaimer.start()
        assert not swept.wait(0.1), 'claim timestamp and rename form one transaction'
    finally:
        continue_claim.set()
        consumer.join(5)
        if reclaimer.ident is not None:
            reclaimer.join(5)
    assert result['message'].id == 'om_1'
    assert result['released'] == 0
    assert box.receive(0) is None


def test_mailbox_defaults_follow_the_global_configuration_directory(tmp_path, monkeypatch):
    monkeypatch.delenv('CO_INBOX_HOME', raising=False)
    monkeypatch.setenv('AGENT_CONFIG_PATH', str(tmp_path / 'global'))
    assert default_home('lark') == (tmp_path / 'global' / 'inbox' / 'lark').resolve()
