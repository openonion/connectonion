"""Asking a co rem command for its help must not move the notebook (#1932).

On 2026-09-30, `co rem projects --help` run from a checkout moved the owner's
real ~/.co/wiki to ~/.co/rem and replaced their daily schedule, while their
installed co was still 1.8.9 and knew no `co rem`. The group callback carried
the old notebook over before Click printed the subcommand's help. Reading a
help page writes no file: that is the help contract every co page is held to.
"""

from pathlib import Path

from typer.testing import CliRunner

from connectonion.cli.main import app


def _old_notebook(home: Path) -> Path:
    old = home / ".co" / "wiki"
    (old / "people").mkdir(parents=True)
    (old / "people" / "someone.md").write_text("# Someone\n")
    return old


def test_a_subcommand_help_page_moves_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    old = _old_notebook(tmp_path)
    for args in (["rem", "projects", "--help"], ["rem", "init", "--help"], ["rem", "investigate", "--help"]):
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, (args, result.output)
        assert old.is_dir() and not (tmp_path / ".co" / "rem").exists(), args
        assert "Moved your notebook" not in result.output


def test_a_real_command_still_carries_the_notebook_over(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    old = _old_notebook(tmp_path)
    CliRunner().invoke(app, ["rem", "list", "people"])
    assert not old.exists() and (tmp_path / ".co" / "rem" / "people" / "someone.md").is_file()
