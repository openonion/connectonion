"""What happens to a session saved while the log is being compacted.

compact() reads every record, writes a temp file, and moves it into place. A
save() landing between the read and the move is written to the file that is
about to be replaced — and vanishes.

The window is small and the placement makes it smaller: compaction runs at
startup, before this process serves anything. It is not zero. `host()` can run
with workers > 1, so a second process may already be serving while this one
starts; the relay announce and the schedule's first tick both begin within
milliseconds of it; and `reconcile_interrupted()` immediately before it writes
to the same file.

A lost session record is a turn that happened and left no trace — the dashboard
never shows it, `co status` never counts it, and nothing anywhere says a record
was dropped. The schedule's state file settled this shape of problem with a
lock; here it is enough to notice, because skipping a compaction costs nothing:
the next startup does it.
"""

import time

import pytest

from connectonion.network.host.session import Session, SessionStorage


@pytest.fixture
def storage(tmp_path):
    return SessionStorage(tmp_path / '.co' / 'sessions.jsonl')


def _expired(storage, n=10):
    past = time.time() - 100
    for i in range(n):
        storage.save(Session(session_id=f"old-{i}", status="done", prompt="x" * 200,
                             created=past - 1000, expires=past))


def _append_while_compactor_has_the_lock(storage, session):
    """Model an append after the compactor's read without waiting 30 seconds.

    The size guard is deliberately a second defence beyond the lock. Calling
    ``save`` here from the same thread cannot model another process: it waits
    for the lock held by ``compact`` until the production timeout expires.
    Appending the same JSONL payload directly isolates the guard this test is
    about and keeps three tests from each paying that 30-second timeout.
    """
    with storage.path.open("a", encoding="utf-8") as stream:
        stream.write(session.model_dump_json() + "\n")


class TestAWriteDuringCompactionSurvives:

    def test_a_session_saved_mid_compaction_is_not_lost(self, storage, monkeypatch):
        _expired(storage)
        now = time.time()

        # A save that lands after compact() has read the file and before it
        # replaces it — which is exactly what a worker serving a request does.
        original = storage._latest_by_id

        def read_then_someone_writes():
            records = original()
            _append_while_compactor_has_the_lock(
                storage,
                Session(session_id="mid", status="done", prompt="a real turn",
                        created=now, expires=now + 3600),
            )
            return records

        monkeypatch.setattr(storage, '_latest_by_id', read_then_someone_writes)
        storage.compact()

        assert storage.get("mid") is not None, (
            "a turn happened and left no trace: the dashboard will never show "
            "it and nothing said a record was dropped"
        )

    def test_compaction_is_skipped_rather_than_half_done(self, storage, monkeypatch):
        """Skipping costs nothing — the next startup compacts."""
        _expired(storage)
        size_before = storage.path.stat().st_size
        now = time.time()
        original = storage._latest_by_id

        def read_then_someone_writes():
            records = original()
            _append_while_compactor_has_the_lock(
                storage,
                Session(session_id="mid", status="done", prompt="p",
                        created=now, expires=now + 3600),
            )
            return records

        monkeypatch.setattr(storage, '_latest_by_id', read_then_someone_writes)
        storage.compact()

        assert storage.path.stat().st_size > size_before


class TestTheQuietPathIsUnchanged:

    def test_compaction_still_happens_when_nobody_writes(self, storage):
        _expired(storage, 20)
        before = storage.path.stat().st_size

        storage.compact()

        assert storage.path.stat().st_size < before / 2

    def test_an_empty_file_is_still_fine(self, storage):
        storage.compact()


class TestStartupDoesNotHingeOnIt:
    """Compaction is housekeeping. It must not be able to stop the agent.

    The same rule `_records` already states for a torn line: "Refusing to boot
    over it costs the agent, so a truncated write or a hand edit is not allowed
    to be fatal."
    """

    def test_the_file_disappearing_mid_compaction_is_not_fatal(self, storage,
                                                               monkeypatch):
        _expired(storage)
        original = storage._latest_by_id

        def read_then_someone_deletes():
            records = original()
            storage.path.unlink()
            return records

        monkeypatch.setattr(storage, '_latest_by_id', read_then_someone_deletes)

        storage.compact()          # must not raise

    def test_no_temp_file_is_left_behind_when_it_skips(self, storage, monkeypatch):
        _expired(storage)
        now = time.time()
        original = storage._latest_by_id

        def read_then_someone_writes():
            records = original()
            _append_while_compactor_has_the_lock(
                storage,
                Session(session_id="mid", status="done", prompt="p",
                        created=now, expires=now + 3600),
            )
            return records

        monkeypatch.setattr(storage, '_latest_by_id', read_then_someone_writes)
        storage.compact()

        leftovers = list(storage.path.parent.glob("*.compact.*"))
        assert leftovers == [], leftovers
