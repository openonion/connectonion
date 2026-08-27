"""Cancellation contracts for interactive terminal input in the async browser."""

import asyncio

import pytest

from connectonion.useful_tools.browser_tools import _async_terminal as terminal


class _FakeStream:
    def __init__(self, line="yes\n"):
        self.line = line

    def fileno(self):
        return 42

    def readline(self):
        return self.line


@pytest.mark.asyncio
async def test_posix_reader_unregisters_descriptor_after_success(monkeypatch):
    real_loop = asyncio.get_running_loop()
    calls = []

    class FakeLoop:
        def create_future(self):
            return real_loop.create_future()

        def add_reader(self, descriptor, callback):
            calls.append(("add", descriptor))
            real_loop.call_soon(callback)

        def remove_reader(self, descriptor):
            calls.append(("remove", descriptor))
            return True

    monkeypatch.setattr(terminal.asyncio, "get_running_loop", lambda: FakeLoop())

    assert await terminal._read_posix_line(_FakeStream()) == "yes"
    assert calls == [("add", 42), ("remove", 42)]


@pytest.mark.asyncio
async def test_posix_reader_unregisters_descriptor_on_cancellation(monkeypatch):
    real_loop = asyncio.get_running_loop()
    calls = []

    class FakeLoop:
        def create_future(self):
            return real_loop.create_future()

        def add_reader(self, descriptor, _callback):
            calls.append(("add", descriptor))

        def remove_reader(self, descriptor):
            calls.append(("remove", descriptor))
            return True

    monkeypatch.setattr(terminal.asyncio, "get_running_loop", lambda: FakeLoop())
    task = asyncio.create_task(terminal._read_posix_line(_FakeStream()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == [("add", 42), ("remove", 42)]


@pytest.mark.asyncio
async def test_windows_reader_is_awaited_and_handles_editing(monkeypatch):
    chars = iter(["y", "e", "x", "\b", "s", "\r"])

    class FakeConsole:
        @staticmethod
        def kbhit():
            return True

        @staticmethod
        def getwch():
            return next(chars)

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(terminal.asyncio, "sleep", no_sleep)
    assert await terminal._read_windows_line(FakeConsole()) == "yes"
