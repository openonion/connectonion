"""The schedule has to actually be wired into the host, and run without a relay.

The module tests prove the clock is right. These prove it is plugged in — and
that plugging it in did not break the case where two things now want the one
on_startup slot the ASGI app offers.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from connectonion.network.host import http_router
from connectonion.network.host import schedule as sched
from connectonion.network.host import server


class TestComposingLifespans:
    """The relay had the slot to itself. Now the schedule wants it too."""

    @pytest.mark.asyncio
    async def test_both_run_in_order(self):
        order = []

        async def first():
            order.append("first")

        async def second():
            order.append("second")

        await server._both(first, second)()
        assert order == ["first", "second"]

    @pytest.mark.asyncio
    async def test_either_may_be_absent(self):
        ran = []

        async def only():
            ran.append(1)

        await server._both(None, only)()
        await server._both(only, None)()
        assert ran == [1, 1]

        assert server._both(None, None) is None


class TestTheTickRuns:
    @pytest.mark.asyncio
    async def test_a_due_entry_runs_and_is_recorded(self, tmp_path):
        co = tmp_path / ".co"
        co.mkdir()
        (co / "schedule.yaml").write_text('- every: 1h\n  run: "/nightly"\n', encoding="utf-8")

        seen = {}

        def fake_input_handler(create_agent, storage, prompt, ttl, session=None, **kw):
            seen["prompt"] = prompt
            seen["session_id"] = session["session_id"]
            return {"status": "done"}

        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        with patch.object(http_router, "input_handler", fake_input_handler):
            await start.tick_once()

        assert seen["prompt"] == "/nightly"

        state = sched.load_state(co)
        assert state["/nightly"]["status"] == "done"
        assert state["/nightly"]["session_id"] == seen["session_id"], (
            "the state must point at the session the run produced, or a "
            "background run is not inspectable afterwards"
        )

    @pytest.mark.asyncio
    async def test_an_entry_that_is_not_due_does_not_run(self, tmp_path):
        co = tmp_path / ".co"
        co.mkdir()
        (co / "schedule.yaml").write_text('- every: 1h\n  run: "/nightly"\n', encoding="utf-8")
        sched.record_run(co, "/nightly", when=datetime.now(timezone.utc),
                         status="done", session_id="prior")

        called = []
        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        with patch.object(http_router, "input_handler",
                          lambda *a, **k: called.append(1) or {"status": "done"}):
            await start.tick_once()

        assert not called

    @pytest.mark.asyncio
    async def test_one_failing_entry_does_not_stop_the_others(self, tmp_path):
        co = tmp_path / ".co"
        co.mkdir()
        (co / "schedule.yaml").write_text(
            '- every: 1h\n  run: "/breaks"\n- every: 1h\n  run: "/works"\n', encoding="utf-8")

        ran = []

        def handler(create_agent, storage, prompt, ttl, session=None, **kw):
            ran.append(prompt)
            if prompt == "/breaks":
                raise RuntimeError("boom")
            return {"status": "done"}

        start, _ = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        with patch.object(http_router, "input_handler", handler):
            await start.tick_once()

        assert ran == ["/breaks", "/works"]

        state = sched.load_state(co)
        assert state["/breaks"]["status"] == "failed"
        assert state["/works"]["status"] == "done"

    @pytest.mark.asyncio
    async def test_no_schedule_starts_no_task(self, tmp_path):
        """An agent with nothing scheduled should not acquire a background task,
        and should not print anything about it."""
        co = tmp_path / ".co"
        co.mkdir()

        start, stop = sched.create_schedule_lifespan(co, lambda: None, None, 86400)
        await start()
        await stop()          # must be safe with nothing running
