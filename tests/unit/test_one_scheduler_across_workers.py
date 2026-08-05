"""`uvicorn --workers 4` runs a scheduled entry four times.

`create_app`'s own docstring tells people to do it:

    app = create_app(create_agent)
    # uvicorn myagent:app --workers 4

That is a real import string, so uvicorn forks four processes and each runs the
lifespan — including the scheduler loop. The overlap guard does not reach across
them:

    if entry.name in in_flight:
        _say(f"{entry.name} still running, skipping this tick")
        continue

`in_flight` is a module-level set, so it is per process. The state file cannot
close the gap either, and the code says why:

    record_run only happens after the turn returns, so last_run is stale for
    the whole duration

So every worker sees the same due entry and starts its own copy. #537 is what
that costs when the entry is not idempotent: two copies of a pipeline that
downloads, extracts and writes to one table racing into the same rows.

#639 fixed the other half — `workers: 2` in host.yaml killing the agent. This is
the path where forking *does* work.

The fix is the smallest thing that spans processes: one lock, taken per tick.
Whichever worker gets it runs that tick; the others skip. Nothing is elected for
the life of the process, so a worker that dies holding it costs one tick — the
OS releases the lock and the next tick has a new winner. `schedule.py` already
locks the state file this way, cross-platform, for the same reason.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from connectonion.network.host import schedule

REPO = Path(__file__).resolve().parents[2]


def _router():
    """The module, not the function of the same name.

    `connectonion.network.host` re-exports a function called `http_router`, so
    the dotted path in monkeypatch.setattr resolves to that and the patch lands
    nowhere. importlib asks for the module.
    """
    import importlib

    return importlib.import_module("connectonion.network.host.http_router")


@pytest.fixture
def co_dir(tmp_path):
    co = tmp_path / ".co"
    co.mkdir()
    (co / "schedule.yaml").write_text(
        '- name: nightly\n  run: "do the thing"\n  every: 1m\n'
    )
    return co


class TestTheTickGuardSpansProcesses:

    def test_only_one_holder_at_a_time(self, co_dir):
        """Two callers, one lock: the second must be refused, not queued."""
        first = schedule._tick_lock(co_dir)
        assert first is not None, "the first caller should hold it"

        assert schedule._tick_lock(co_dir) is None, \
            "a second caller took the lock while the first held it"

        schedule._release_tick_lock(first)

    def test_it_is_available_again_once_released(self, co_dir):
        handle = schedule._tick_lock(co_dir)
        schedule._release_tick_lock(handle)

        second = schedule._tick_lock(co_dir)
        assert second is not None, "the lock was not released"
        schedule._release_tick_lock(second)

    def test_a_dead_holder_does_not_keep_it(self, co_dir):
        """The OS releases a flock when the process dies — that is the property
        that makes per-tick election self-healing rather than a leader that has
        to be reaped.

        A real second process, because that is the whole claim. `fork` is not
        available on Windows and a spawned child cannot pickle a local, so this
        goes through the interpreter directly.
        """
        code = ("from pathlib import Path;"
                "from connectonion.network.host import schedule as s;"
                f"s._tick_lock(Path({str(co_dir)!r}));"
                "import os; os._exit(0)")
        proc = subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                              capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr[-300:]

        handle = schedule._tick_lock(co_dir)
        assert handle is not None, "a dead worker's lock outlived it"
        schedule._release_tick_lock(handle)


class TestATickDoesNotRunTwice:

    @pytest.mark.asyncio
    async def test_the_second_worker_skips_while_the_first_holds_it(self, co_dir, monkeypatch):
        """The behaviour the whole issue is about, at the tick boundary."""
        ran = []

        def fake_input_handler(create_agent, storage, prompt, result_ttl, session=None, **kw):
            ran.append(prompt)
            return {"status": "done", "session_id": session["session_id"]}

        monkeypatch.setattr(_router(), "input_handler", fake_input_handler)

        on_startup, _ = schedule.create_schedule_lifespan(
            co_dir, lambda: None, storage=None, result_ttl=60)

        held = schedule._tick_lock(co_dir)          # another worker is mid-tick
        try:
            await on_startup.tick_once()
        finally:
            schedule._release_tick_lock(held)

        assert ran == [], f"a second worker ran the entry anyway: {ran}"

    @pytest.mark.asyncio
    async def test_the_entry_still_runs_when_nobody_else_holds_it(self, co_dir, monkeypatch):
        """The other half: a lock that refuses everyone stops the schedule dead."""
        ran = []

        def fake_input_handler(create_agent, storage, prompt, result_ttl, session=None, **kw):
            ran.append(prompt)
            return {"status": "done", "session_id": session["session_id"]}

        monkeypatch.setattr(_router(), "input_handler", fake_input_handler)

        on_startup, _ = schedule.create_schedule_lifespan(
            co_dir, lambda: None, storage=None, result_ttl=60)
        await on_startup.tick_once()

        assert ran == ["do the thing"], f"the only worker did not run it: {ran}"

    @pytest.mark.asyncio
    async def test_the_lock_is_released_for_the_next_tick(self, co_dir, monkeypatch):
        """Held for the tick, not for the process — else worker 2 never wins again."""
        monkeypatch.setattr(_router(), "input_handler",
                            lambda *a, **kw: {"status": "done", "session_id": "s"})

        on_startup, _ = schedule.create_schedule_lifespan(
            co_dir, lambda: None, storage=None, result_ttl=60)
        await on_startup.tick_once()

        handle = schedule._tick_lock(co_dir)
        assert handle is not None, "tick_once kept the lock after it finished"
        schedule._release_tick_lock(handle)

    @pytest.mark.asyncio
    async def test_a_failing_entry_still_releases_it(self, co_dir, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("the turn died")

        monkeypatch.setattr(_router(), "input_handler", boom)

        on_startup, _ = schedule.create_schedule_lifespan(
            co_dir, lambda: None, storage=None, result_ttl=60)
        await on_startup.tick_once()

        handle = schedule._tick_lock(co_dir)
        assert handle is not None, "a failed entry left the schedule locked forever"
        schedule._release_tick_lock(handle)


class TestFourWorkersLikeUvicornForks:
    """The issue's actual claim, with four real processes.

    Everything above drives one process holding a lock on behalf of another.
    That is a fake of the situation, and a fake that agrees with the fix is how
    the last several of these survived. So: four interpreters, started together,
    each running one tick against one `.co/` — the shape `uvicorn --workers 4`
    produces — and one line in the log per run.
    """

    WORKER = (
        "import asyncio, sys\n"
        "from pathlib import Path\n"
        "from connectonion.network.host import schedule\n"
        "import importlib\n"
        "router = importlib.import_module('connectonion.network.host.http_router')\n"
        "co = Path(sys.argv[1])\n"
        "def handler(create_agent, storage, prompt, result_ttl, session=None, **kw):\n"
        "    with open(co / 'runs.log', 'a') as fh:\n"
        "        fh.write(prompt + '\\n')\n"
        "    return {'status': 'done', 'session_id': session['session_id']}\n"
        "router.input_handler = handler\n"
        "on_startup, _ = schedule.create_schedule_lifespan(co, lambda: None, None, 60)\n"
        "asyncio.run(on_startup.tick_once())\n"
    )

    def test_the_entry_runs_once_not_four_times(self, co_dir):
        workers = [
            subprocess.Popen([sys.executable, "-c", self.WORKER, str(co_dir)],
                             cwd=str(REPO), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True)
            for _ in range(4)
        ]
        for worker in workers:
            out, err = worker.communicate(timeout=300)
            assert worker.returncode == 0, err[-400:]

        log = co_dir / "runs.log"
        runs = log.read_text().splitlines() if log.exists() else []

        assert runs == ["do the thing"], f"{len(runs)} workers ran it: {runs}"
