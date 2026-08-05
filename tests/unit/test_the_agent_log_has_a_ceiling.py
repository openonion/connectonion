"""`.co/logs/{agent}.log` grows forever.

Measured in #638. On the deployed naturewill agent over ~3.3 days:

    .co/logs/naturewill.log   1.46 MB  ->  ~0.44 MB/day  =  ~160 MB/year

That one fails fast every run and logs a large error block each time, so it is
the high end. A working agent, three tool-using turns, is ~1.3 KB per turn —
125 KB/day on a fifteen-minute schedule, ~44 MB/year.

Neither number fills the 1–2 GB VPS `co server new` provisions any time soon,
which is why #638 was filed rather than fixed. But unbounded is unbounded, and
1.6.0 is meant to run for years without anyone looking at it. #637's evals were
the fast member of the same family (3.5 GB/year) and were capped; this is the
slow one.

Rotation, not truncation: at the cap the file becomes `.log.1` and a fresh one
starts. One generation is kept, so the ceiling is two files. Deleting history
outright would take away the thing an operator goes to the log for.

What is deliberately not done is anything time-based or configurable. An
operator who wants a different policy points logrotate at the directory, which
works because these are ordinary append-only text files — and stays working
because rotation happens on open, not from a background thread.
"""

from pathlib import Path

import pytest

from connectonion.console import Console, LOG_MAX_BYTES


@pytest.fixture
def log(tmp_path):
    return tmp_path / "logs" / "agent.log"


class TestTheFileHasACeiling:

    def test_a_small_log_is_left_alone(self, log):
        Console(log_file=log)
        first = log.read_text(encoding="utf-8")

        Console(log_file=log)

        assert log.read_text(encoding="utf-8").startswith(first)
        assert not (log.parent / "agent.log.1").exists()

    def test_an_oversized_log_is_rotated(self, log):
        log.parent.mkdir(parents=True)
        log.write_text("x" * (LOG_MAX_BYTES + 1), encoding="utf-8")

        Console(log_file=log)

        assert (log.parent / "agent.log.1").exists(), sorted(
            p.name for p in log.parent.iterdir())

    def test_the_old_content_is_kept_not_deleted(self, log):
        log.parent.mkdir(parents=True)
        log.write_text("the evidence" + "x" * LOG_MAX_BYTES, encoding="utf-8")

        Console(log_file=log)

        assert "the evidence" in (log.parent / "agent.log.1").read_text(
            encoding="utf-8", errors="replace")

    def test_the_new_file_starts_fresh(self, log):
        log.parent.mkdir(parents=True)
        log.write_text("old" + "x" * LOG_MAX_BYTES, encoding="utf-8")

        Console(log_file=log)
        text = log.read_text(encoding="utf-8")

        assert "old" not in text
        assert "Session started" in text

    def test_only_one_generation_is_kept(self, log):
        """The ceiling is two files, not a growing pile of .log.N."""
        log.parent.mkdir(parents=True)
        for _ in range(3):
            log.write_text("y" * (LOG_MAX_BYTES + 1), encoding="utf-8")
            Console(log_file=log)

        rotated = sorted(p.name for p in log.parent.iterdir() if ".log." in p.name)
        assert rotated == ["agent.log.1"], rotated

    def test_the_newest_history_wins(self, log):
        """A second rotation replaces .log.1 rather than keeping the older one."""
        log.parent.mkdir(parents=True)
        log.write_text("older" + "x" * LOG_MAX_BYTES, encoding="utf-8")
        Console(log_file=log)
        log.write_text("newer" + "x" * LOG_MAX_BYTES, encoding="utf-8")
        Console(log_file=log)

        kept = (log.parent / "agent.log.1").read_text(encoding="utf-8", errors="replace")
        assert "newer" in kept and "older" not in kept


class TestTheCeilingIsSane:

    def test_it_is_measured_in_megabytes(self):
        """Small enough to bound growth, large enough that a real session fits.
        #638 measured ~1.3 KB per turn and 1.46 MB over three days."""
        assert 1_000_000 <= LOG_MAX_BYTES <= 100_000_000, LOG_MAX_BYTES


class TestNothingElseChanges:

    def test_a_missing_directory_is_still_created(self, tmp_path):
        log = tmp_path / "deep" / "logs" / "agent.log"

        Console(log_file=log)

        assert log.exists()

    def test_no_log_file_is_still_fine(self):
        assert Console(log_file=None).log_file is None

    def test_the_session_header_is_still_written(self, log):
        Console(log_file=log)

        assert "Session started" in log.read_text(encoding="utf-8")
