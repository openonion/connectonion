"""Unit tests for interruptible blocking agent steps."""

import threading
import time

import pytest

from connectonion.core.interrupt import run_interruptible


class MailboxIO:
    def __init__(self, messages=None):
        self.messages = list(messages or [])
        self.lock = threading.Lock()

    def send_to_agent(self, message):
        with self.lock:
            self.messages.append(message)

    def receive_all(self, msg_type=None):
        with self.lock:
            if msg_type is None:
                result = list(self.messages)
                self.messages.clear()
                return result
            matched = [m for m in self.messages if m.get("type") == msg_type]
            self.messages[:] = [m for m in self.messages if m.get("type") != msg_type]
            return matched


def test_direct_call_without_io_has_no_worker_thread():
    caller = threading.get_ident()

    result, interrupted = run_interruptible(threading.get_ident, None)

    assert result == caller
    assert interrupted is False


def test_pending_interrupt_prevents_step_from_starting():
    io = MailboxIO([{"type": "INTERRUPT"}])
    started = False

    def step():
        nonlocal started
        started = True

    result, interrupted = run_interruptible(step, io, poll_seconds=0.01)

    assert result is None
    assert interrupted is True
    assert started is False


def test_interrupt_abandons_slow_step_and_preserves_other_messages():
    io = MailboxIO([{"type": "mode_change", "mode": "safe"}])
    started = threading.Event()
    release = threading.Event()

    def step():
        started.set()
        release.wait(timeout=2)
        return "late"

    def interrupt():
        assert started.wait(timeout=1)
        io.send_to_agent({"type": "INTERRUPT"})

    threading.Thread(target=interrupt, daemon=True).start()
    before = time.monotonic()
    result, interrupted = run_interruptible(step, io, poll_seconds=0.01)
    elapsed = time.monotonic() - before
    release.set()

    assert result is None
    assert interrupted is True
    assert elapsed < 0.3
    assert io.receive_all() == [{"type": "mode_change", "mode": "safe"}]


def test_completed_step_wins_same_poll_window():
    class RaceIO(MailboxIO):
        def __init__(self):
            super().__init__()
            self.polls = 0

        def receive_all(self, msg_type=None):
            self.polls += 1
            if self.polls == 1:
                return []
            return [{"type": "INTERRUPT"}]

    io = RaceIO()

    result, interrupted = run_interruptible(
        lambda: (time.sleep(0.01), "done")[1],
        io,
        poll_seconds=0.1,
    )

    assert result == "done"
    assert interrupted is False
    assert io.polls == 1


def test_worker_exception_is_reraised_on_caller_thread():
    def fail():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_interruptible(fail, MailboxIO(), poll_seconds=0.01)
