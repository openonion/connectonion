"""
LLM-Note: Tests for connectonion.inbox.consumer — the loop that hands inbox
messages to a handler. One lane per conversation: ordered inside a lane,
parallel across lanes, leases renewed while a handler runs, and a message that
keeps coming back is given up rather than retried forever.
"""

import threading
import time

import pytest

from connectonion.inbox.store import Inbox, Message


def box(tmp_path, name="feishu"):
    return Inbox(name, home=tmp_path / name)


def put(inbox, message_id, chat="c1", thread=None, text="hi"):
    inbox.deliver(Message(id=message_id, chat=chat, thread=thread, sender="s1",
                          text=text, at="2026-09-11T00:00:00Z"))


def drain(inbox, handler, **options):
    """Run serve() until the queue is empty, with a hard stop so a bug in the
    loop fails the test instead of hanging the suite."""
    options.setdefault("workers", 4)
    options.setdefault("idle_seconds", 0.3)
    stop = threading.Event()
    thread = threading.Thread(target=inbox.serve, args=(handler,),
                              kwargs={"should_stop": stop, **options}, daemon=True)
    thread.start()
    return stop, thread


def settle(inbox, stop, thread, *, until, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not until():
        time.sleep(0.02)
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "serve did not stop when asked"


class TestOneLanePerConversation:
    def test_messages_in_one_conversation_are_handled_one_at_a_time_in_order(self, tmp_path):
        inbox = box(tmp_path)
        for n in range(4):
            put(inbox, f"m{n}", chat="c1")
        seen, overlap = [], []
        running = threading.Lock()

        def handler(message):
            if not running.acquire(blocking=False):
                overlap.append(message.id)
            else:
                time.sleep(0.02)
                seen.append(message.id)
                running.release()

        stop, thread = drain(inbox, handler)
        settle(inbox, stop, thread, until=lambda: len(seen) == 4)
        assert seen == ["m0", "m1", "m2", "m3"]
        assert overlap == [], "two handlers ran at once in a single conversation"

    def test_different_conversations_do_not_wait_for_each_other(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "slow", chat="slow-chat")
        put(inbox, "quick", chat="quick-chat")
        finished = []

        def handler(message):
            if message.id == "slow":
                time.sleep(1.0)
            finished.append(message.id)

        stop, thread = drain(inbox, handler)
        settle(inbox, stop, thread, until=lambda: len(finished) == 2, timeout=15)
        # The quick conversation answered while the slow one was still working.
        assert finished[0] == "quick"

    def test_a_thread_is_a_lane_not_a_message(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "a", chat="c1", thread="t1")
        put(inbox, "b", chat="c1", thread="t2")
        lanes = set()

        def handler(message):
            lanes.add(threading.current_thread().name)
            time.sleep(0.05)

        stop, thread = drain(inbox, handler)
        settle(inbox, stop, thread, until=lambda: len(lanes) == 2)
        assert len(lanes) == 2, "two threads of one chat shared a lane"


class TestOutcome:
    def test_a_handler_that_returns_finishes_the_message(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "m1")
        stop, thread = drain(inbox, lambda message: None)
        settle(inbox, stop, thread, until=lambda: inbox.completed.exists())
        assert list(inbox.cur.iterdir()) == []
        assert "m1" in inbox.completed.read_text()

    def test_a_handler_that_raises_leaves_the_message_for_the_sweep(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "m1")
        tried = threading.Event()

        def handler(message):
            tried.set()
            raise RuntimeError("the model was down")

        stop, thread = drain(inbox, handler)
        settle(inbox, stop, thread, until=tried.is_set)
        # Still taken, not completed: an hour from now the sweep offers it again.
        assert [p.name.split("-", 1)[1] for p in inbox.cur.iterdir()] == ["m1"]
        assert not inbox.completed.exists()
        assert "m1 not finished: RuntimeError: the model was down" in inbox.logfile.read_text()


class TestLease:
    def test_a_long_handler_keeps_its_lease_so_the_sweep_does_not_take_it_back(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "m1")
        working, release = threading.Event(), threading.Event()
        renewals = []
        real_renew = inbox.renew

        def counted(message_id):
            result = real_renew(message_id)
            renewals.append(message_id)
            return result

        inbox.renew = counted

        def handler(message):
            working.set()
            release.wait(10)

        stop, thread = drain(inbox, handler, lease_seconds=0.05)
        assert working.wait(10)
        # Wait for renewals to have demonstrably happened, not for a duration.
        # A fixed sleep asserts that a background thread was scheduled inside
        # a wall-clock window, which a loaded CI runner does not promise — this
        # test failed exactly that way on 3.11 before it was written this way.
        deadline = time.monotonic() + 10
        while len(renewals) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(renewals) >= 2, "the lease was never renewed"

        # The claim was made long before the last renewal, so a window that
        # would have reclaimed it finds nothing: the timestamp moved.
        assert inbox.release_stale(max_age=0.05) == 0, "the renewal did not move the clock"
        release.set()
        settle(inbox, stop, thread, until=lambda: inbox.completed.exists())

    def test_without_a_lease_the_sweep_reclaims_a_slow_handler(self, tmp_path):
        """The opposite case, so the test above proves the renewal and not the clock."""
        inbox = box(tmp_path)
        put(inbox, "m1")
        inbox.receive(timeout=0)
        time.sleep(0.3)
        assert inbox.release_stale(max_age=0.2) == 1


class TestGivingUp:
    def test_a_claim_is_counted(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "m1")
        assert inbox.attempts("m1") == 0
        inbox.receive(timeout=0)
        assert inbox.attempts("m1") == 1
        inbox.release_stale(max_age=0)
        inbox.receive(timeout=0)
        assert inbox.attempts("m1") == 2

    def test_a_message_that_keeps_coming_back_is_given_up_not_retried_forever(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "m1")
        for _ in range(3):                      # three handouts already survived
            inbox.receive(timeout=0)
            inbox.release_stale(max_age=0)
        calls = []

        stop, thread = drain(inbox, lambda message: calls.append(message.id), max_attempts=3)
        settle(inbox, stop, thread, until=lambda: inbox.completed.exists())
        assert calls == [], "a poison message reached the handler a fourth time"
        assert "m1" in inbox.completed.read_text()
        assert "gave up" in inbox.logfile.read_text()

    def test_a_message_under_the_limit_still_reaches_the_handler(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "m1")
        inbox.receive(timeout=0)
        inbox.release_stale(max_age=0)
        calls = []
        stop, thread = drain(inbox, lambda message: calls.append(message.id), max_attempts=3)
        settle(inbox, stop, thread, until=lambda: calls == ["m1"])
        assert calls == ["m1"]


class TestConcurrencyCap:
    def test_no_more_than_workers_handlers_run_at_once(self, tmp_path):
        inbox = box(tmp_path)
        for n in range(6):
            put(inbox, f"m{n}", chat=f"c{n}")     # six lanes, all ready at once
        live, peak = threading.Semaphore(0), []
        counter = {"now": 0}
        guard = threading.Lock()
        done = threading.Event()

        def handler(message):
            with guard:
                counter["now"] += 1
                peak.append(counter["now"])
            time.sleep(0.1)
            with guard:
                counter["now"] -= 1
                if len(peak) == 6:
                    done.set()

        stop, thread = drain(inbox, handler, workers=2)
        settle(inbox, stop, thread, until=done.is_set, timeout=15)
        assert max(peak) <= 2, f"the cap of 2 was exceeded: {peak}"

    def test_an_idle_lane_stops_instead_of_leaking_a_thread(self, tmp_path):
        inbox = box(tmp_path)
        put(inbox, "m1", chat="c1")
        before = threading.active_count()
        stop, thread = drain(inbox, lambda message: None, idle_seconds=0.1)
        settle(inbox, stop, thread, until=lambda: inbox.completed.exists())
        time.sleep(0.5)
        assert threading.active_count() <= before + 1
