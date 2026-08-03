"""What a long-running agent's session log costs after a few months.

`save()` appends and nothing ever removes. `expires` is honoured on *read* —
`list()` and `get()` skip records past their TTL — but the records stay in the
file, and `list()` parses all of them to answer.

Measured on a live agent: 17 MB for 222 sessions, about 77 KB each. One running
a schedule every 15 minutes writes 96 a day:

    ~7 MB a day     ~2.5 GB a year

Two costs, and the second is the one people feel. The disk fills, and the
dashboard — which calls `list()` — parses the whole file every time it is
opened, forever.

Compaction is safe here for a specific reason: it drops only what `list()` and
`get()` already refuse to return. An expired record is invisible to every
reader before it is removed, so removing it changes nothing anyone can observe
except the size of the file.
"""

import json
import time

import pytest

from connectonion.network.host.session import Session, SessionStorage


def _write(storage, **kw):
    storage.save(Session(**kw))


@pytest.fixture
def storage(tmp_path):
    return SessionStorage(tmp_path / '.co' / 'sessions.jsonl')


class TestExpiredRecordsLeave:

    def test_the_file_shrinks(self, storage):
        past = time.time() - 100
        for i in range(20):
            _write(storage, session_id=f"old-{i}", status="done", prompt="x" * 500,
                   created=past - 1000, expires=past)
        before = storage.path.stat().st_size

        storage.compact()

        assert storage.path.stat().st_size < before / 2, (
            f"{before} → {storage.path.stat().st_size}"
        )

    def test_what_readers_can_see_is_unchanged(self, storage):
        now = time.time()
        _write(storage, session_id="live", status="done", prompt="keep",
               created=now, expires=now + 3600)
        _write(storage, session_id="gone", status="done", prompt="drop",
               created=now - 1000, expires=now - 100)

        before = {s.session_id for s in storage.list()}
        storage.compact()
        after = {s.session_id for s in storage.list()}

        assert before == after == {"live"}

    def test_a_running_session_survives_whatever_its_ttl_says(self, storage):
        """`running` is exempt from the TTL on read, so it is exempt here."""
        past = time.time() - 100
        _write(storage, session_id="busy", status="running", prompt="working",
               created=past - 1000, expires=past)

        storage.compact()

        assert storage.get("busy") is not None

    def test_only_the_newest_record_per_session_is_kept(self, storage):
        """Every turn appends a fresh record for the same id; readers use the
        last one, so the earlier ones are already invisible."""
        now = time.time()
        for turn in range(5):
            _write(storage, session_id="s1", status="done", prompt=f"turn {turn}",
                   created=now, expires=now + 3600)

        storage.compact()

        assert storage.path.read_text().count('"session_id"') == 1
        assert storage.get("s1").prompt == "turn 4"


class TestItIsSafeToRunAtStartup:

    def test_an_empty_file_is_fine(self, storage):
        storage.compact()          # must not raise

    def test_a_torn_line_does_not_stop_it(self, storage):
        """Same rule as _records: one unreadable record is not an unreadable
        file, and startup must not hinge on it."""
        now = time.time()
        _write(storage, session_id="ok", status="done", prompt="p",
               created=now, expires=now + 3600)
        with open(storage.path, 'a', encoding='utf-8') as f:
            f.write('{"session_id": "torn", "stat\n')

        storage.compact()

        assert storage.get("ok") is not None

    def test_nothing_is_lost_when_nothing_has_expired(self, storage):
        now = time.time()
        for i in range(5):
            _write(storage, session_id=f"s{i}", status="done", prompt="p",
                   created=now, expires=now + 3600)

        storage.compact()

        assert len(storage.list()) == 5


class TestItIsActuallyCalled:
    """A compaction nothing invokes is a function, not a fix.

    `get_default_trust()` in this repo was exactly that for seven months —
    correct, tested in isolation, never called — so the check here is that the
    startup path names it, not that it works in a vacuum.
    """

    def test_the_host_compacts_on_startup(self):
        import importlib
        import inspect

        server = importlib.import_module('connectonion.network.host.server')
        source = inspect.getsource(server)

        assert source.count("storage.compact()") >= 1, (
            "nothing calls compact(), so the file still grows forever"
        )

    def test_it_runs_beside_the_other_startup_reconciliation(self):
        """Both walk the same file; doing them apart means reading it twice."""
        import importlib
        import inspect

        server = importlib.import_module('connectonion.network.host.server')
        lines = inspect.getsource(server).splitlines()
        reconcile = [i for i, l in enumerate(lines) if "reconcile_interrupted()" in l]
        compact = [i for i, l in enumerate(lines) if "storage.compact()" in l]

        assert compact, "compact() is not in the startup path"
        assert min(abs(c - r) for c in compact for r in reconcile) <= 3
