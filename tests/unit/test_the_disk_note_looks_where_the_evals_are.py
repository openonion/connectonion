"""The disk note reads ~/.co/evals. A project agent fills the project's .co/evals.

`disk_usage_note()` exists because the largest thing `co` writes was the one thing
the diagnostic did not report. It looks in one place:

    evals = Path.home() / ".co" / "evals"

and its docstring frames the growth as `co ai`'s, which does write there. But the
logger writes to the *project's* `.co/evals/` whenever an agent runs inside a
project — measured, running the shipped quickstart from a fresh `co init`:

    /…/freshproj/.co/evals/what_is_42_17.yaml

That is the normal case for the library: `Agent(...)` in someone's project. So the
uncapped growth the note was written for happens in a directory the note never
opens, while it reports a global one that a project user may barely use.

On the machine this was found on the two are far apart:

    ~/.co/evals              1085 evals   237 MB   ← reported
    <worktree>/.co/evals       40 evals   652 KB   ← not

The worktree's is small, which is why this is a gap rather than a wrong number:
below the 20 MB threshold the note stays quiet by design, and a project that has
crossed it says nothing at all.
"""

from pathlib import Path

import pytest

from connectonion.cli.commands import doctor_commands as dc


def _fill(evals_dir: Path, mb: int, count: int = 3) -> None:
    """Write `count` eval dirs totalling roughly `mb` megabytes."""
    evals_dir.mkdir(parents=True, exist_ok=True)
    per_file = (mb * 1024 * 1024) // count
    for i in range(count):
        one = evals_dir / f"prompt_{i}"
        one.mkdir(exist_ok=True)
        (one / "run_1.yaml").write_bytes(b"x" * per_file)
        (evals_dir / f"prompt_{i}.yaml").write_text("name: prompt\n")


@pytest.fixture
def empty_home(monkeypatch, tmp_path):
    """A HOME with no evals, so anything reported comes from the project."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


class TestTheProjectsEvalsAreReported:

    def test_a_big_project_evals_dir_is_noticed(self, empty_home, tmp_path, monkeypatch):
        project = tmp_path / "proj"
        _fill(project / ".co" / "evals", mb=40)
        monkeypatch.chdir(project)

        note = dc.disk_usage_note()

        assert note, "a 40 MB project evals directory produced no note"

    def test_the_note_names_the_project_directory(self, empty_home, tmp_path, monkeypatch):
        project = tmp_path / "proj"
        _fill(project / ".co" / "evals", mb=40)
        monkeypatch.chdir(project)

        note = dc.disk_usage_note()

        assert ".co/evals" in note
        assert "~/.co/evals" != note.strip()

    def test_a_small_project_dir_stays_quiet(self, empty_home, tmp_path, monkeypatch):
        """Below the threshold a line printed every run is a line nobody reads."""
        project = tmp_path / "proj"
        _fill(project / ".co" / "evals", mb=1)
        monkeypatch.chdir(project)

        assert dc.disk_usage_note() is None


class TestTheGlobalDirectoryIsStillReported:
    """The case the note was written for, unchanged."""

    def test_a_big_home_evals_dir_is_noticed(self, empty_home, tmp_path, monkeypatch):
        _fill(empty_home / ".co" / "evals", mb=40)
        monkeypatch.chdir(tmp_path)

        note = dc.disk_usage_note()

        assert note and "evals" in note

    def test_both_are_reported_when_both_are_big(self, empty_home, tmp_path, monkeypatch):
        _fill(empty_home / ".co" / "evals", mb=40)
        project = tmp_path / "proj"
        _fill(project / ".co" / "evals", mb=40, count=5)
        monkeypatch.chdir(project)

        note = dc.disk_usage_note()

        assert note.count("evals") >= 2, note


class TestNothingToReport:

    def test_no_evals_anywhere_is_silent(self, empty_home, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        assert dc.disk_usage_note() is None

    def test_a_project_without_a_co_directory_is_silent(self, empty_home, tmp_path,
                                                       monkeypatch):
        (tmp_path / "plain").mkdir()
        monkeypatch.chdir(tmp_path / "plain")

        assert dc.disk_usage_note() is None
