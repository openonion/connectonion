"""Two writers must not destroy each other's state.

`record_run` is called whenever an entry finishes. One process running entries
in sequence rarely overlaps — but a deploy restart does: the old process is
still finishing a turn while the new one boots and records its own, and the
lock beside the file exists precisely for that case.
"""

import json
import threading
from datetime import datetime, timezone

from connectonion.network.host.schedule import record_run, load_state


def test_concurrent_writers_do_not_raise(tmp_path):
    """The temp file was one shared name, so writers deleted each other's."""
    now = datetime.now(timezone.utc)
    errors = []

    def write(i):
        try:
            for _ in range(20):
                record_run(tmp_path, f"entry{i % 4}", when=now,
                           status="done", session_id=f"s{i}")
        except Exception as exc:      # noqa: BLE001 - the assertion is the message
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(12)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert not errors, errors[:3]


def test_no_entry_is_lost(tmp_path):
    """Every name that was written must survive. A dropped entry means the
    scheduler forgets an entry ever ran, and runs it again."""
    now = datetime.now(timezone.utc)

    def write(i):
        for _ in range(20):
            record_run(tmp_path, f"entry{i % 4}", when=now,
                       status="done", session_id=f"s{i}")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(12)]
    for t in threads: t.start()
    for t in threads: t.join()

    state = load_state(tmp_path)
    assert sorted(state) == ["entry0", "entry1", "entry2", "entry3"]


def test_the_file_is_never_left_unparseable(tmp_path):
    now = datetime.now(timezone.utc)

    def write(i):
        for _ in range(15):
            record_run(tmp_path, f"e{i}", when=now, status="done", session_id="s")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    raw = (tmp_path / "schedule-state.json").read_text(encoding="utf-8")
    json.loads(raw)          # must not raise


def test_no_temp_files_are_left_behind(tmp_path):
    """A unique temp name must still be cleaned up, or the directory fills."""
    now = datetime.now(timezone.utc)

    def write(i):
        for _ in range(10):
            record_run(tmp_path, f"e{i}", when=now, status="done", session_id="s")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()

    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert not leftovers, leftovers[:5]


def test_writing_without_the_lock_is_not_silent(tmp_path, capsys, monkeypatch):
    """Giving up on the lock and writing anyway is a decision, not a detail.

    _lock retries for a second and then returns None, and record_run proceeds
    regardless — deliberately, because blocking forever on a lock held by a
    process the OS never noticed dying is worse. But an unlocked
    read-modify-write can still lose another writer's entry, and a lost
    last_run makes the scheduler run something twice. That has to be findable
    afterwards, in the log, not inferred from a duplicate run.
    """
    from datetime import datetime, timezone
    from connectonion.network.host import schedule as sch

    monkeypatch.setattr(sch, "_lock", lambda *a, **k: None)

    sch.record_run(tmp_path, "nightly", when=datetime.now(timezone.utc),
                   status="done", session_id="s1")

    out = capsys.readouterr().out + capsys.readouterr().err
    assert "lock" in out.lower(), f"nothing said about the missing lock: {out!r}"


def test_a_normal_write_says_nothing(tmp_path, capsys):
    """The warning has to be rare enough to mean something."""
    from datetime import datetime, timezone
    from connectonion.network.host.schedule import record_run

    record_run(tmp_path, "nightly", when=datetime.now(timezone.utc),
               status="done", session_id="s1")

    assert "lock" not in capsys.readouterr().out.lower()
