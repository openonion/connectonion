"""A long-running agent never compacts, and compacting while it runs loses turns.

`compact()` is called from exactly two places, both startup:

    compact() called inside: host()        (server.py:479)
    compact() called inside: create_app()  (server.py:725)

So an agent that is not restarted never compacts — which is the ordinary case
for what 1.6.0 is meant to support, something put on a server and left alone.
Its own docstring is the argument:

    a live agent was at 17 MB for 222 sessions … One running a schedule every
    fifteen minutes writes 96 a day, so about 7 MB a day and 2.5 GB a year

Measured on nw-e2e, up ~15 hours: 494106 bytes, 73 lines.

## Why it cannot simply be called more often

The existing guard reads the file size, builds the replacement, reads the size
again, and skips if it changed. Between that second read and the `replace`
there is still a window, and an append that lands in it is in the file being
thrown away:

    size_when_read = self.path.stat().st_size
    ...build tmp...
    unchanged = self.path.stat().st_size == size_when_read      <- here
    tmp.replace(self.path)                                      <- and here

At startup that window is small and nothing is serving. On a live agent it is
an ordinary turn. `compact()` says as much: "A lost session record is a turn
that happened and left no trace."

So the fix is not moving the call. It is making the append and the replace
mutually exclusive, with the same cross-process lock `schedule.py` already uses
for its state file — after which compaction can run whenever, and the
scheduler tick (already elected to one process per cluster since #687) is the
natural moment.
"""

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from connectonion.network.host.session import SessionStorage
from connectonion.network.host.session.storage import Session


REPO = Path(__file__).resolve().parents[2]


def _session(sid: str, created: float) -> Session:
    return Session(session_id=sid, status="done", prompt="p", result="r",
                   created=created, expires=created + 10_000)


@pytest.fixture
def storage(tmp_path):
    return SessionStorage(path=tmp_path / "sessions.jsonl")


class TestAnAppendDuringCompactionSurvives:

    def test_a_turn_written_mid_compaction_is_still_there(self, storage, monkeypatch):
        """The window the old guard left open, driven at its narrowest point.

        The append comes from another thread, which is the real shape -- the
        host serves turns in threads, and `host()` can run workers > 1 -- and
        it is released at the last possible moment, after the guard has
        satisfied itself that nothing changed and before the replace.

        The first version of this test appended from *this* thread, which
        cannot happen: an append and a compaction in one thread are ordered by
        being one thread. It was testing a scenario the code never faces.
        """
        import threading

        for i in range(5):
            storage.save(_session(f"old-{i}", time.time()))

        original_replace = Path.replace
        writer_done = threading.Event()

        def replace_after_an_append(self, target):
            if not writer_done.is_set():
                def write():
                    storage.save(_session("mid-compaction", time.time()))
                    writer_done.set()
                thread = threading.Thread(target=write)
                thread.start()
                # Long enough that the append is genuinely in flight; the lock
                # is what has to hold it, not the timing.
                thread.join(timeout=2)
            return original_replace(self, target)

        monkeypatch.setattr(Path, "replace", replace_after_an_append)
        storage.compact()
        writer_done.wait(timeout=10)

        assert storage.get("mid-compaction") is not None, (
            "the turn written during compaction left no trace"
        )

    def test_the_older_records_are_still_there_too(self, storage):
        for i in range(5):
            storage.save(_session(f"old-{i}", time.time()))

        storage.compact()

        assert all(storage.get(f"old-{i}") for i in range(5))


class TestConcurrentWritersAndCompactors:
    """Real processes, because the lock has to hold across them -- `host()` can
    run workers > 1, which is the case the startup guard already admits it does
    not cover."""

    WORKER = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(REPO)!r})
        from pathlib import Path
        from connectonion.network.host.session import SessionStorage
        from connectonion.network.host.session.storage import Session

        path, tag, mode = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
        storage = SessionStorage(path=path)
        for i in range(25):
            if mode == "write":
                now = time.time()
                storage.save(Session(session_id=f"{{tag}}-{{i}}", status="done",
                                     prompt="p", result="r", created=now,
                                     expires=now + 10_000))
            else:
                storage.compact()
    """)

    def test_no_turn_is_lost(self, tmp_path):
        path = tmp_path / "sessions.jsonl"
        procs = [
            subprocess.Popen([sys.executable, "-c", self.WORKER, str(path), tag, mode])
            for tag, mode in [("a", "write"), ("b", "write"), ("c", "write"),
                              ("x", "compact"), ("y", "compact")]
        ]
        for proc in procs:
            assert proc.wait(timeout=600) == 0

        storage = SessionStorage(path=path)
        missing = [f"{tag}-{i}" for tag in ("a", "b", "c") for i in range(25)
                   if storage.get(f"{tag}-{i}") is None]

        assert not missing, f"{len(missing)} of 75 turns lost: {missing[:6]}"


class TestCompactionStillCompacts:

    def test_superseded_records_go(self, storage):
        now = time.time()
        for _ in range(4):
            storage.save(_session("same-id", now))
        before = storage.path.stat().st_size

        storage.compact()

        assert storage.path.stat().st_size < before
        assert storage.get("same-id") is not None

    def test_expired_records_go(self, storage):
        old = time.time() - 100_000
        storage.save(Session(session_id="stale", status="done", prompt="p",
                             created=old, expires=old + 1))
        storage.save(_session("fresh", time.time()))

        storage.compact()

        assert storage.get("stale") is None
        assert storage.get("fresh") is not None

    def test_a_running_session_is_never_dropped(self, storage):
        old = time.time() - 100_000
        storage.save(Session(session_id="busy", status="running", prompt="p",
                             created=old, expires=old + 1))

        storage.compact()

        assert storage.get("busy") is not None

    def test_a_missing_file_is_not_an_error(self, tmp_path):
        SessionStorage(path=tmp_path / "never-written.jsonl").compact()


class TestTheTickCompacts:
    """The other half: an agent left running has to compact without a restart."""

    def _lifespan(self, co_dir, storage):
        from connectonion.network.host.schedule import create_schedule_lifespan

        (co_dir / "schedule.yaml").write_text(
            '- name: nightly\n  run: "do it"\n  every: 1m\n', encoding="utf-8")
        return create_schedule_lifespan(co_dir, lambda: None, storage, result_ttl=60)

    @pytest.mark.asyncio
    async def test_a_tick_compacts(self, tmp_path, monkeypatch):
        import importlib

        co_dir = tmp_path / ".co"
        co_dir.mkdir()
        storage = SessionStorage(path=co_dir / "sessions.jsonl")
        now = time.time()
        for _ in range(6):
            storage.save(_session("same", now))
        before = storage.path.stat().st_size

        router = importlib.import_module("connectonion.network.host.http_router")
        monkeypatch.setattr(router, "input_handler",
                            lambda *a, **kw: {"status": "done", "session_id": "s"})
        on_startup, _ = self._lifespan(co_dir, storage)
        await on_startup.tick_once()

        assert storage.path.stat().st_size < before
        assert storage.get("same") is not None

    @pytest.mark.asyncio
    async def test_a_tick_without_storage_does_not_crash(self, tmp_path, monkeypatch):
        """`create_schedule_lifespan` is called with storage=None in tests and
        in any host that does not persist sessions."""
        import importlib

        co_dir = tmp_path / ".co"
        co_dir.mkdir()
        router = importlib.import_module("connectonion.network.host.http_router")
        monkeypatch.setattr(router, "input_handler",
                            lambda *a, **kw: {"status": "done", "session_id": "s"})
        on_startup, _ = self._lifespan(co_dir, None)

        await on_startup.tick_once()
