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
