"""Nothing tells you `~/.co` has grown, and on this machine it is 227 MB.

`co ai` writes an eval per distinct first prompt, plus a directory of runs for
it. Runs inside one eval are capped — KEEP_RUNS_PER_EVAL = 20, and the trim runs
after every write — but the number of *evals* is not capped by anything. A
one-off prompt leaves its directory behind for good.

Measured on the machine this was found on:

    ~/.co/evals   857 yaml files + 858 run directories, 227 MB

`co doctor` reports system, configuration, browser, skills and connectivity. It
is the command people run when something looks off, and it says nothing about
the largest thing `co` writes. Neither does `co status`.

Not a bug in the trim: a copy of the worst directory (367 runs, from before the
cap existed) went to 20 when _trim_old_runs was called on it, keeping the newest
— so old directories self-heal the next time that eval runs. What does not
self-heal is an eval that is never run again.

This adds the number, not a deletion. Which evals are worth keeping is the
user's call; not being able to see the size is what stops them making it.
"""

import pytest


@pytest.fixture(autouse=True)
def _standing_in_an_empty_project(tmp_path, monkeypatch):
    """The note also reads the project's .co/evals, found by walking up from the
    cwd. Left alone that is the repo's, which other xdist workers' agents are
    writing and trimming during a full run (#1653) — so these tests read a
    directory they did not make, whose size and contents change under them.
    Standing in a project of our own makes the note see only what the test wrote."""
    project = tmp_path / "project"
    (project / ".co").mkdir(parents=True)
    monkeypatch.chdir(project)


@pytest.fixture
def co_dir(tmp_path, monkeypatch):
    """A ~/.co with evals of a known size."""
    home = tmp_path / "home"
    (home / ".co" / "evals").mkdir(parents=True)
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    return home / ".co"


def _make_evals(co_dir, count, kilobytes_each):
    for index in range(count):
        (co_dir / "evals" / f"eval_{index}.yaml").write_text(
            "x" * (kilobytes_each * 1024), encoding="utf-8"
        )


class TestItReportsTheSize:

    def test_a_large_evals_directory_is_reported(self, co_dir):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        _make_evals(co_dir, count=40, kilobytes_each=1024)  # ~40 MB

        note = disk_usage_note()

        assert note, "40 MB of evals and doctor says nothing"

    def test_the_note_names_the_directory(self, co_dir):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        _make_evals(co_dir, count=40, kilobytes_each=1024)

        assert "evals" in disk_usage_note()

    def test_the_note_gives_a_size(self, co_dir):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        _make_evals(co_dir, count=40, kilobytes_each=1024)

        assert "MB" in disk_usage_note()

    def test_it_says_how_many_evals(self, co_dir):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        _make_evals(co_dir, count=40, kilobytes_each=1024)

        assert "40" in disk_usage_note()


class TestItStaysQuietWhenThereIsNothingToSay:
    """A note on every run is a note nobody reads."""

    def test_a_small_directory_is_not_reported(self, co_dir):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        _make_evals(co_dir, count=3, kilobytes_each=10)

        assert disk_usage_note() is None

    def test_an_empty_directory_is_not_reported(self, co_dir):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        assert disk_usage_note() is None

    def test_a_missing_directory_is_not_an_error(self, tmp_path, monkeypatch):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "nowhere")

        assert disk_usage_note() is None


class TestItIsNotAProblem:
    """Disk use is information, not a failure — doctor's ✗ count must not move."""

    def test_it_is_not_counted_as_a_problem(self, co_dir):
        from connectonion.cli.commands import doctor_commands

        _make_evals(co_dir, count=40, kilobytes_each=1024)

        note = doctor_commands.disk_usage_note()

        assert "problem" not in note.lower()
        assert "✗" not in note


class TestAnAgentTrimmingItsEvalsMeanwhile:
    """#1653. The logger trims old runs after every write, so a running agent
    deletes files and run directories under .co/evals while doctor walks it.
    The full suite does exactly that: other workers' agents write and trim the
    repo's .co/evals, which this note also reads. An entry listed and then gone
    by the time it is opened must be skipped, not crash `co doctor`."""

    def _vanish_after_listing(self, monkeypatch, victim):
        import os

        real = os.scandir

        def remove(path):
            # Not shutil.rmtree: it walks with os.scandir, which is patched here.
            if path.is_dir():
                for name in os.listdir(path):
                    os.unlink(path / name)
                path.rmdir()
            else:
                path.unlink()

        class Listing:
            def __init__(self, path):
                self._it = real(path)
                self._entries = list(self._it)

            def __enter__(self):
                return self

            def __iter__(self):
                # Listed; now the agent trims it, before anyone opens or stats it.
                if victim.exists():
                    remove(victim)
                return iter(self._entries)

            def __exit__(self, *exc):
                self._it.close()

        monkeypatch.setattr("connectonion.cli.commands.doctor_commands.os.scandir", Listing)

    def test_a_run_directory_removed_mid_walk_is_skipped(self, co_dir, monkeypatch):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        _make_evals(co_dir, count=40, kilobytes_each=1024)
        runs = co_dir / "evals" / "eval_0"
        runs.mkdir()
        (runs / "run_1.yaml").write_text("old run")
        self._vanish_after_listing(monkeypatch, runs)

        assert "40" in disk_usage_note()

    def test_a_file_removed_mid_walk_is_skipped(self, co_dir, monkeypatch):
        from connectonion.cli.commands.doctor_commands import disk_usage_note

        _make_evals(co_dir, count=41, kilobytes_each=1024)
        self._vanish_after_listing(monkeypatch, co_dir / "evals" / "eval_40.yaml")

        assert disk_usage_note()
