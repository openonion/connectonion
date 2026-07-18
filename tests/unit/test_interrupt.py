"""Tests for abandoning blocking agent steps on user interrupt."""

import threading
import time

import pytest

from connectonion.core.interrupt import run_interruptible


class MailboxIO:
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.lock = threading.Lock()

    def receive_all(self, msg_type=None):
        with self.lock:
            matched = [m for m in self.messages if msg_type is None or m.get("type") == msg_type]
            self.messages = [m for m in self.messages if m not in matched]
            return matched

    def send_to_agent(self, message):
        with self.lock:
            self.messages.append(message)


def test_without_interrupt_capable_io_runs_inline():
    caller_thread = threading.get_ident()

    result, interrupted = run_interruptible(threading.get_ident, io=None)

    assert result == caller_thread
    assert interrupted is False


def test_selective_receive_without_requeue_runs_inline():
    class ReceiveOnlyIO:
        def receive_all(self, msg_type=None):
            return []

    caller_thread = threading.get_ident()

    result, interrupted = run_interruptible(threading.get_ident, ReceiveOnlyIO())

    assert result == caller_thread
    assert interrupted is False


def test_inline_exception_propagates():
    def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_interruptible(fail, io=None)


def test_pending_interrupt_prevents_step_from_starting():
    called = False
    io = MailboxIO([{"type": "mode_change"}, {"type": "INTERRUPT"}])

    def work():
        nonlocal called
        called = True

    result, interrupted = run_interruptible(work, io)

    assert result is None
    assert interrupted is True
    assert called is False
    assert io.messages == [{"type": "mode_change"}]


def test_interrupt_abandons_running_step_within_poll_bound():
    io = MailboxIO()
    started = threading.Event()
    release = threading.Event()

    def work():
        started.set()
        release.wait(timeout=2)
        return "late"

    timer = threading.Thread(
        target=lambda: (started.wait(timeout=1), io.send_to_agent({"type": "INTERRUPT"})),
        daemon=True,
    )
    timer.start()
    began = time.monotonic()
    result, interrupted = run_interruptible(work, io, poll_seconds=0.02)
    elapsed = time.monotonic() - began
    release.set()

    assert result is None
    assert interrupted is True
    assert elapsed < 0.3


def test_completed_step_wins_same_window_race():
    class RaceIO:
        def __init__(self):
            self.calls = 0
            self.release = threading.Event()
            self.completed = threading.Event()
            self.messages = []

        def receive_all(self, msg_type=None):
            self.calls += 1
            if self.calls == 1:
                return []
            self.release.set()
            assert self.completed.wait(timeout=1)
            return [{"type": "INTERRUPT"}]

        def send_to_agent(self, message):
            self.messages.append(message)

    io = RaceIO()

    def work():
        io.release.wait(timeout=1)
        io.completed.set()
        return "finished"

    result, interrupted = run_interruptible(work, io, poll_seconds=0.05)

    assert result == "finished"
    assert interrupted is False
    assert io.calls == 2
    assert io.messages == [{"type": "INTERRUPT"}]


def test_worker_exception_re_raises_on_caller_thread():
    io = MailboxIO()

    def fail():
        raise ValueError("worker failed")

    with pytest.raises(ValueError, match="worker failed"):
        run_interruptible(fail, io)
