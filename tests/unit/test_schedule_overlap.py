"""An entry that overruns its interval must not be started again. #537.

`record_run` happens after the turn returns, so `last_run` is stale for the
whole duration of a run. An entry configured `every: 15m` whose work takes
twenty minutes is due again at minute fifteen — while the first copy is still
working — and again at thirty.

Not only wasted compute: two copies of the contract pipeline download, extract
and write to the same table, racing each other into the same rows.

The runs here take 200ms rather than blocking, so a missing fix shows up as a
failed assertion rather than a hung test.
"""

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.network.host import http_router
from connectonion.network.host import schedule as sched


def a_schedule(tmp_path, text='- name: slow\n  every: 1m\n  run: "/slow"\n'):
    co = tmp_path / ".co"
    co.mkdir(exist_ok=True)
    (co / "schedule.yaml").write_text(text, encoding="utf-8")
    return co


class Recorder:
    """Counts how many copies of each entry are inside the handler at once."""

    def __init__(self, seconds=0.2):
        self.seconds = seconds
        self.lock = threading.Lock()
        self.inside = 0
        self.peak = 0
        self.starts = []

    def __call__(self, create_agent, storage, prompt, ttl, session=None, **kw):
        with self.lock:
            self.starts.append(prompt)
            self.inside += 1
            self.peak = max(self.peak, self.inside)
        try:
            time.sleep(self.seconds)
            return {"status": "done"}
        finally:
            with self.lock:
                self.inside -= 1


class TestOneAtATime:
    @pytest.mark.asyncio
    async def test_a_tick_does_not_start_a_run_already_in_flight(self, tmp_path, monkeypatch):
        co = a_schedule(tmp_path)
        rec = Recorder()
        monkeypatch.setattr(http_router, "input_handler", rec)

        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)

        first = asyncio.create_task(start.tick_once())
        await asyncio.sleep(0.05)                 # the first run is inside
        await start.tick_once()                   # a tick lands mid-run
        await first

        assert rec.peak == 1, (
            f"{rec.peak} copies of one entry ran at once; two copies of a "
            "pipeline race each other into the same table"
        )
        assert len(rec.starts) == 1

    @pytest.mark.asyncio
    async def test_it_runs_again_once_the_first_has_finished(self, tmp_path, monkeypatch):
        co = a_schedule(tmp_path)
        rec = Recorder(seconds=0)
        monkeypatch.setattr(http_router, "input_handler", rec)

        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        await start.tick_once()
        await start.tick_once(now=datetime.now(timezone.utc) + timedelta(hours=1))

        assert len(rec.starts) == 2, "the in-flight flag outlived the run"

    @pytest.mark.asyncio
    async def test_a_run_that_raised_does_not_stay_marked_in_flight(self, tmp_path, monkeypatch):
        """If the flag survived a crash the entry would never run again."""
        co = a_schedule(tmp_path)
        calls = []

        def blows_up(create_agent, storage, prompt, ttl, session=None, **kw):
            calls.append(prompt)
            raise RuntimeError("boom")

        monkeypatch.setattr(http_router, "input_handler", blows_up)

        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        await start.tick_once()
        await start.tick_once(now=datetime.now(timezone.utc) + timedelta(hours=1))

        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_a_busy_entry_does_not_hold_up_a_different_one(self, tmp_path, monkeypatch):
        co = a_schedule(tmp_path,
                        '- name: slow\n  every: 1m\n  run: "/slow"\n'
                        '- name: quick\n  every: 1m\n  run: "/quick"\n')
        rec = Recorder()
        monkeypatch.setattr(http_router, "input_handler", rec)

        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        await start.tick_once()

        assert set(rec.starts) == {"/slow", "/quick"}


class TestOneEntryCannotStopTheRest:
    """#1681: entries ran one after another under the tick lock."""

    @pytest.mark.asyncio
    async def test_a_slow_entry_does_not_delay_another(self, tmp_path, monkeypatch):
        co = a_schedule(tmp_path,
                        '- name: slow\n  every: 1m\n  run: "/slow"\n'
                        '- name: quick\n  every: 1m\n  run: "/quick"\n')
        started = {}
        release = threading.Event()

        def handler(create_agent, storage, prompt, ttl, session=None, **kw):
            started[prompt] = time.monotonic()
            if prompt == "/slow":
                release.wait(5)
            return {"status": "done"}

        monkeypatch.setattr(http_router, "input_handler", handler)
        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        tick = asyncio.create_task(start.tick_once())
        deadline = time.monotonic() + 2
        while "/quick" not in started and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        release.set()
        await tick

        assert "/quick" in started and started["/quick"] - started["/slow"] < 1, (
            "the quick entry waited for the slow one to finish"
        )

    @pytest.mark.asyncio
    async def test_a_run_in_progress_does_not_hold_the_next_tick(self, tmp_path, monkeypatch):
        co = a_schedule(tmp_path,
                        '- name: slow\n  every: 1m\n  run: "/slow"\n')
        release = threading.Event()
        runs = []

        def handler(create_agent, storage, prompt, ttl, session=None, **kw):
            runs.append(prompt)
            release.wait(5)
            return {"status": "done"}

        monkeypatch.setattr(http_router, "input_handler", handler)
        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        first = asyncio.create_task(start.tick_once())
        await asyncio.sleep(0.1)
        (co / "schedule.yaml").write_text(
            '- name: slow\n  every: 1m\n  run: "/slow"\n'
            '- name: new\n  every: 1m\n  run: "/new"\n', encoding="utf-8")
        second = asyncio.create_task(start.tick_once())
        deadline = time.monotonic() + 2
        while "/new" not in runs and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        release.set()
        await asyncio.gather(first, second)

        assert runs.count("/slow") == 1, "a second copy of a running entry started"
        assert "/new" in runs, "the next tick waited for the running entry"


class TestAScheduleAddedLaterStillRuns:
    """#1682: no entries at startup meant no clock, until a restart."""

    @pytest.mark.asyncio
    async def test_the_clock_starts_with_nothing_scheduled(self, tmp_path, monkeypatch):
        co = tmp_path / ".co"
        co.mkdir()
        start, stop = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        ran = []
        monkeypatch.setattr(http_router, "input_handler",
                            lambda *a, **k: ran.append(a[2]) or {"status": "done"})
        monkeypatch.setattr(sched, "TICK_SECONDS", 0.05)
        await start()
        (co / "schedule.yaml").write_text('- every: 1h\n  run: "/later"\n', encoding="utf-8")
        deadline = time.monotonic() + 3
        while not ran and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        await stop()

        assert ran == ["/later"]

    @pytest.mark.asyncio
    async def test_a_mark_left_by_a_dead_process_is_cleared_at_startup(self, tmp_path):
        co = tmp_path / ".co"
        co.mkdir()
        sched.record_run(co, "x", when=datetime.now(timezone.utc), status="running", session_id="s")
        start, stop = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        await start()
        await stop()

        state = sched.load_state(co)["x"]
        assert state["status"] == "failed" and "stopped" in state["reason"]
