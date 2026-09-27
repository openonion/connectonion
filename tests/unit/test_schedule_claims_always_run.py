"""A claimed entry runs, a requested run survives the run it arrived during,
and a timed-out command is actually stopped. #1756.

Three ways the scheduler's state said one thing while the process did another:

1. `_claim_due` writes `status: running` before anything runs, and the
   Control Center's `extra_tick` and session compaction ran between the claim
   and the runs. If either raised, the claimed entries were never started — and
   every later tick skipped them as "still running" until the agent restarted.

2. `co schedule run X` sets `run_requested` and says "will run within a
   minute". If X was mid-run, the completion rewrote X's state keeping only
   `paused`, so the request was erased and nothing ran.

3. An `exec:` entry runs with `shell=True` and a timeout. On timeout only the
   shell was killed; the command it started kept going while the state said
   `failed`, and the next tick started a second copy beside it.
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from connectonion.network.host import schedule as sched


def a_schedule(tmp_path, text):
    co = tmp_path / ".co"
    co.mkdir(exist_ok=True)
    (co / "schedule.yaml").write_text(text, encoding="utf-8")
    return co


def state(co):
    return json.loads((co / "schedule-state.json").read_text(encoding="utf-8"))


class TestAFailingExtraTickDoesNotStrandTheClaim:
    @pytest.mark.asyncio
    async def test_the_claimed_entry_still_runs(self, tmp_path):
        marker = tmp_path / "ran.txt"
        co = a_schedule(tmp_path, f"- name: report\n  every: 15m\n  exec: touch {marker}\n")

        async def flaky(now):
            raise RuntimeError("control center: network blip")

        start, _ = sched.create_schedule_lifespan(co, None, None, 60, extra_tick=flaky)
        with pytest.raises(RuntimeError):
            await start.tick_once()

        assert marker.exists(), "the claimed entry never ran"
        assert state(co)["report"]["status"] == "done", (
            f"left as {state(co)['report']} — every later tick skips it as still running")

    @pytest.mark.asyncio
    async def test_a_failing_compaction_does_not_strand_it_either(self, tmp_path):
        marker = tmp_path / "ran.txt"
        co = a_schedule(tmp_path, f"- name: report\n  every: 15m\n  exec: touch {marker}\n")

        class BrokenStorage:
            def compact(self):
                raise OSError("disk full")

        start, _ = sched.create_schedule_lifespan(co, None, BrokenStorage(), 60)
        with pytest.raises(OSError):
            await start.tick_once()

        assert marker.exists()
        assert state(co)["report"]["status"] == "done"


class TestARunRequestedMidRunIsKept:
    @pytest.mark.asyncio
    async def test_the_request_survives_the_run_it_arrived_during(self, tmp_path):
        co = a_schedule(tmp_path, "- name: report\n  every: 1d\n  exec: sleep 0.6\n")
        start, _ = sched.create_schedule_lifespan(co, None, None, 60)

        run = asyncio.create_task(start.tick_once())
        await asyncio.sleep(0.2)
        sched.set_flag(co, "report", "run_requested", True)   # `co schedule run report`
        await run

        assert state(co)["report"].get("run_requested") is True, (
            "the completion erased the request; `co schedule run` promised a run that never comes")

    @pytest.mark.asyncio
    async def test_it_runs_on_the_next_tick_and_is_then_consumed(self, tmp_path):
        marker = tmp_path / "count.txt"
        co = a_schedule(tmp_path, f"- name: report\n  every: 1d\n  exec: echo x >> {marker}\n")
        start, _ = sched.create_schedule_lifespan(co, None, None, 60)
        await start.tick_once()
        sched.set_flag(co, "report", "run_requested", True)

        await start.tick_once()
        await start.tick_once()

        assert marker.read_text().count("x") == 2, "requested once, so one extra run"
        assert "run_requested" not in state(co)["report"]


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are POSIX")
class TestATimedOutCommandIsStopped:
    @pytest.mark.asyncio
    async def test_the_command_does_not_outlive_its_timeout(self, tmp_path, monkeypatch):
        marker = tmp_path / "orphan.txt"
        # A second shell, like any real script that forks: killing only the
        # outer `sh` is what left this one running.
        co = a_schedule(tmp_path, "- name: slow\n  every: 1d\n"
                                  f"  exec: /bin/sh -c 'sleep 1.5; touch {marker}'\n")
        monkeypatch.setattr(sched, "EXEC_TIMEOUT_SECONDS", 0.5)
        start, _ = sched.create_schedule_lifespan(co, None, None, 60)

        began = time.monotonic()
        await start.tick_once()
        assert time.monotonic() - began < 1.4, "the tick waited for the command, not the timeout"
        await asyncio.sleep(2.0)

        assert not marker.exists(), "the timed-out command kept running and finished anyway"
        recorded = state(co)["slow"]
        assert recorded["status"] == "failed"
        assert "timed out" in recorded.get("reason", "")
