"""Concurrency contract for the 1.8 browser daemon.

The wire may accept many clients at once, but one asyncio-owned browser runtime
decides what can overlap: independent tabs progress together, one tab is ordered,
and a claim race has exactly one winner.  Cancellation must remove only the
request-scoped audit lease; durable tab ownership remains governed by the
existing guard/declared-hold rules.
"""

import asyncio
import json
import time

import pytest

from connectonion.cli.browser_agent import daemon as daemon_module
from connectonion.cli.browser_agent.daemon import BrowserDaemon
from connectonion.useful_tools.browser_tools._async_browser import AsyncBrowserCore


def envelope(line: str, *, caller: str, tab: str | None = None) -> str:
    return json.dumps(
        {"v": 1, "caller": caller, "account": "", "tab": tab, "line": line}
    )


class TimedBrowser(AsyncBrowserCore):
    """No-driver probe that uses the real core's operation and tab locks."""

    def __init__(self):
        super().__init__(headless=True)
        self.intervals: list[tuple[str | None, float, float]] = []
        self.started = asyncio.Event()

    async def slow(self, seconds: float = 0.1) -> str:
        async with self._tab_operation(ensure_page=False):
            key = self._bound_session_key()
            start = time.monotonic()
            self.started.set()
            try:
                await asyncio.sleep(seconds)
            finally:
                self.intervals.append((key, start, time.monotonic()))
            return f"finished {key}"


@pytest.fixture
def daemon(tmp_path):
    server = BrowserDaemon(str(tmp_path / "browser.sock"), headless=True)
    server.browser = TimedBrowser()
    return server


def test_daemon_owns_async_core_without_global_browser_executor(tmp_path):
    server = BrowserDaemon(str(tmp_path / "browser.sock"), headless=True)

    assert isinstance(server.browser, AsyncBrowserCore)
    assert not hasattr(server.browser, "_executor")


async def open_tab(server: BrowserDaemon, name: str, caller: str) -> None:
    ok, payload = await server.dispatch_async(
        envelope(f"tab open {name} --who {caller}", caller=caller)
    )
    assert ok is True, payload


@pytest.mark.asyncio
async def test_independent_tabs_make_progress_concurrently(daemon):
    await open_tab(daemon, "left", "left-agent")
    await open_tab(daemon, "right", "right-agent")

    started = time.monotonic()
    results = await asyncio.gather(
        daemon.dispatch_async(envelope("slow 0.15", caller="left-agent", tab="left")),
        daemon.dispatch_async(envelope("slow 0.15", caller="right-agent", tab="right")),
    )
    elapsed = time.monotonic() - started

    assert [result[0] for result in results] == [True, True]
    assert elapsed < 0.26, "independent tabs were serialized by a global lane"
    left, right = daemon.browser.intervals
    assert min(left[2], right[2]) > max(left[1], right[1]), "operations did not overlap"


@pytest.mark.asyncio
async def test_same_tab_operations_are_serialized(daemon):
    await open_tab(daemon, "only", "agent")

    started = time.monotonic()
    results = await asyncio.gather(
        daemon.dispatch_async(envelope("slow 0.1", caller="agent", tab="only")),
        daemon.dispatch_async(envelope("slow 0.1", caller="agent", tab="only")),
    )
    elapsed = time.monotonic() - started

    assert [result[0] for result in results] == [True, True]
    assert elapsed >= 0.18
    first, second = daemon.browser.intervals
    assert first[2] <= second[1]


@pytest.mark.asyncio
async def test_two_callers_racing_for_main_have_one_auditable_winner(daemon):
    gate = asyncio.Event()

    async def contend(caller: str):
        await gate.wait()
        return await daemon.dispatch_async(envelope("slow 0.05", caller=caller))

    tasks = [
        asyncio.create_task(contend("agent-a")),
        asyncio.create_task(contend("agent-b")),
    ]
    gate.set()
    results = await asyncio.gather(*tasks)

    outcomes = [0 if result[0] is True else result[0] for result in results]
    assert sorted(outcomes) == [0, 4]
    assert len(daemon.browser.intervals) == 1
    meta = daemon.browser._tab_meta[None]
    assert meta["caller"] in {"agent-a", "agent-b"}
    assert meta["last_line"] == "slow 0.05"
    assert "active_requests" not in meta


@pytest.mark.asyncio
async def test_cancelled_request_clears_only_its_active_lease(daemon):
    task = asyncio.create_task(
        daemon.dispatch_async(envelope("slow 30", caller="owner"))
    )
    await daemon.browser.started.wait()

    meta = daemon.browser._tab_meta[None]
    assert len(meta["active_requests"]) == 1
    ok, payload = await daemon.dispatch_async(
        envelope("tab ls --json", caller="observer")
    )
    assert ok is True
    active = json.loads(payload)[0]["active_requests"]
    assert len(active) == 1
    assert active[0]["caller"] == "owner"
    assert active[0]["line"] == "slow 30"
    assert active[0]["request_id"]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "active_requests" not in meta
    assert meta["caller"] == "owner", "cancellation erased durable ownership"
    assert daemon.browser._active_operations == 0
    assert daemon.browser._operations_idle.is_set()


@pytest.mark.asyncio
async def test_request_reader_rejects_oversized_payload(daemon, monkeypatch):
    monkeypatch.setattr(daemon_module, "MAX_REQUEST_BYTES", 32)
    reader = asyncio.StreamReader()
    reader.feed_data(b"x" * 33)
    reader.feed_eof()

    with pytest.raises(ValueError, match="32-byte limit"):
        await daemon._read_posix_request(reader)


@pytest.mark.asyncio
async def test_request_deadline_bounds_a_stalled_client(daemon, monkeypatch):
    monkeypatch.setattr(daemon_module, "REQUEST_TIMEOUT", 0.02)
    reader = asyncio.StreamReader()

    with pytest.raises(TimeoutError, match="request timed out"):
        await daemon._read_posix_request(reader)


class FakeTransport:
    def __init__(self):
        self.aborted = False

    def abort(self):
        self.aborted = True


class BlockingWriter:
    def __init__(self):
        self.transport = FakeTransport()
        self.payload = b""
        self.closed = False

    def write(self, payload: bytes):
        self.payload += payload

    async def drain(self):
        await asyncio.Future()

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


@pytest.mark.asyncio
async def test_slow_reader_cannot_hold_a_connection_forever(daemon, monkeypatch):
    monkeypatch.setattr(daemon_module, "REPLY_TIMEOUT", 0.02)
    reader = asyncio.StreamReader()
    reader.feed_data(envelope("status", caller="observer").encode())
    reader.feed_eof()
    writer = BlockingWriter()

    await daemon._handle_posix_client(reader, writer)

    assert writer.payload.startswith(b"OK\n")
    assert writer.closed is True


@pytest.mark.asyncio
async def test_connection_cap_sheds_excess_without_spawning_more_work(daemon):
    blockers = {
        asyncio.create_task(asyncio.sleep(30))
        for _ in range(daemon_module.MAX_IN_FLIGHT)
    }
    daemon._client_tasks.update(blockers)
    writer = BlockingWriter()

    daemon._accept_posix_client(asyncio.StreamReader(), writer)

    assert writer.transport.aborted is True
    assert daemon._client_tasks == blockers
    for task in blockers:
        task.cancel()
    await asyncio.gather(*blockers, return_exceptions=True)


class WakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_windows_shutdown_discards_the_connection_that_wakes_accept(
    daemon, monkeypatch
):
    connection = WakeConnection()

    async def accepted(_fn):
        daemon._closing = True
        return connection

    monkeypatch.setattr(daemon, "_transport_call", accepted)

    await daemon._serve_windows()

    assert connection.closed is True
    assert daemon._client_tasks == set()


def test_windows_shutdown_wakes_accept_before_closing_the_listener(
    daemon, monkeypatch
):
    submitted = []

    class Loop:
        def run_in_executor(self, pool, fn):
            submitted.append((pool, fn))

    class Listener:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    listener = Listener()
    pool = object()
    daemon._loop = Loop()
    daemon._transport_pool = pool
    daemon._srv = listener
    monkeypatch.setattr(daemon_module.transport, "IS_WINDOWS", True)

    daemon._begin_shutdown()

    assert daemon._closing is True
    assert listener.closed is False
    assert submitted == [(pool, daemon._wake_windows_accept)]
