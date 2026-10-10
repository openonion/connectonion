"""co wiki became co rem in 1.9.0 (#1932): a 1.8.x notebook, its daily schedule
and a wrapper's program variable come across without being lost or doubled."""

import plistlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem import migrate
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError
from connectonion.rem.schedule import Launchd

runner = CliRunner()


def old_notebook() -> Path:
    old = Path.home() / ".co" / "wiki"
    prepare(old)
    Notebook(old).write("people/alice.md", "# Alice\nWorks on Aurora.")
    return old


def test_the_first_co_rem_moves_the_old_notebook_rather_than_copying_it():
    old = old_notebook()
    result = runner.invoke(app, ["rem", "list", "people"])
    new = Path.home() / ".co" / "rem"
    assert result.exit_code == 0, result.output
    assert "Moved your notebook from" in result.output
    assert not old.exists() and "Aurora" in Notebook(new).read("people/alice.md")
    again = runner.invoke(app, ["rem", "list", "people"])
    assert "Moved" not in again.output


def test_both_folders_are_refused_and_neither_is_touched():
    old = old_notebook()
    new = Path.home() / ".co" / "rem"
    prepare(new)
    result = runner.invoke(app, ["rem", "status"])
    assert result.exit_code == 1
    assert str(old) in result.output and str(new) in result.output and "never merged" in result.output
    assert (old / "people/alice.md").is_file() and not (new / "people/alice.md").exists()


def test_an_explicit_root_is_used_as_given(tmp_path):
    old = old_notebook()
    prepare(tmp_path / "mine")
    result = runner.invoke(app, ["rem", "--root", str(tmp_path / "mine"), "status"])
    assert result.exit_code == 0, result.output
    assert (old / "people/alice.md").is_file() and not (Path.home() / ".co" / "rem").exists()


def test_a_move_that_fails_leaves_the_old_folder_whole(monkeypatch):
    old = old_notebook()

    def refuse(source, target):
        raise PermissionError("read-only")

    monkeypatch.setattr(migrate.os, "rename", refuse)
    result = runner.invoke(app, ["rem", "status"])
    assert result.exit_code == 1
    assert (old / "people/alice.md").read_text().endswith("Works on Aurora.")


def test_a_schedule_that_runs_co_wiki_is_replaced_by_one_that_runs_co_rem(tmp_path):
    calls = []
    run = lambda args, **kw: calls.append(args) or type("R", (), {"returncode": 0, "stdout": ""})()
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    old, new = tmp_path / "wiki", tmp_path / "rem"
    prepare(new)
    stale = agents / "ai.openonion.co-wiki.0123456789ab.plist"
    stale.write_bytes(plistlib.dumps({"Label": "ai.openonion.co-wiki.0123456789ab",
                                      "ProgramArguments": ["/bin/co", "wiki", "--root", str(old), "sync", "--scheduled"]}))
    other = agents / "ai.openonion.co-wiki.ba9876543210.plist"
    other.write_bytes(plistlib.dumps({"Label": "x", "ProgramArguments": ["co", "wiki", "--root", "/elsewhere", "sync"]}))
    scheduler = Launchd(agents_dir=agents, uid=501, run=run, command=["/bin/co"])

    line = migrate.replace_schedule(new, old, scheduler)

    assert line == "Your daily update now runs co rem sync."
    assert not stale.exists() and other.exists(), "only this notebook's job is replaced"
    installed = plistlib.loads(scheduler.plist_path(new).read_bytes())
    assert installed["ProgramArguments"][:2] == ["/usr/bin/caffeinate", "-i"]
    assert "rem" in installed["ProgramArguments"] and "--root" in installed["ProgramArguments"]
    assert ["launchctl", "bootout", "gui/501/ai.openonion.co-wiki.0123456789ab"] in calls
    assert migrate.replace_schedule(new, old, scheduler) == ""


def test_the_old_program_variable_still_names_the_wrapper_with_a_notice(monkeypatch, tmp_path):
    monkeypatch.delenv("CO_REM_PROGRAM", raising=False)
    monkeypatch.setenv("CO_WIKI_PROGRAM", "remi")
    assert migrate.program() == "remi"
    assert "CO_REM_PROGRAM" in migrate.old_program_notice()
    result = runner.invoke(app, ["rem", "--root", str(tmp_path / "n"), "status"])
    assert "Next: remi --root" in result.output and "deprecated" in result.output
    monkeypatch.setenv("CO_REM_PROGRAM", "remy")
    assert migrate.program() == "remy" and migrate.old_program_notice() == ""


@pytest.mark.parametrize("args", [["status"], ["--root", "/tmp/n", "logs", "--usage"]])
def test_co_wiki_runs_nothing_and_names_the_same_command_under_co_rem(args):
    old = old_notebook()
    result = runner.invoke(app, ["wiki", *args])
    lines = [line for line in result.output.splitlines() if line.startswith("Next:")]
    assert result.exit_code == 2
    assert "co wiki is now co rem." in result.output
    assert lines == ["Next: co rem " + " ".join(args)]
    assert old.exists(), "the tombstone moves nothing"
