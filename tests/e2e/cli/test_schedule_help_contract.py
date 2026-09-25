"""`co schedule` help meets the #1643 contract: reachable, honest about side effects, runnable examples."""

import re
import shlex

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()
GROUP = get_command(app).commands["schedule"]
LEAVES = sorted(GROUP.commands)
READ_ONLY = {"list", "check"}
# CI sets FORCE_COLOR, so Rich writes colour codes between the words.
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def help_of(*words):
    return ANSI.sub("", runner.invoke(app, [*words, "--help"], terminal_width=200).stdout)


def test_the_root_help_reaches_the_group():
    assert re.search(r"^│ schedule\s", help_of(), re.M)


def test_the_group_lists_every_command_and_names_its_way_back():
    page = help_of("schedule")
    for leaf in LEAVES:
        assert re.search(rf"^│ {leaf}\s", page, re.M), leaf
    assert "Back: co --help" in page and "never edits schedule.yaml" in page


@pytest.mark.parametrize("leaf", LEAVES)
def test_every_leaf_says_its_side_effect_has_an_example_and_a_way_back(leaf):
    page = help_of("schedule", leaf)
    assert ("Read-only" in page) == (leaf in READ_ONLY), leaf
    assert ("Writes schedule state" in page) == (leaf not in READ_ONLY), leaf
    assert "Back: co schedule --help" in page
    example = re.search(r"Example:\s+(co schedule [^|]+?)\s+\|", page).group(1)
    words = shlex.split(example)
    assert words[2] == leaf
    options = {opt for param in GROUP.commands[leaf].params for opt in param.opts}
    assert all(word in options for word in words[3:] if word.startswith("--")), example


def test_help_never_writes_state(tmp_path, monkeypatch):
    (tmp_path / ".co").mkdir()
    (tmp_path / ".co" / "schedule.yaml").write_text('- every: 1h\n  run: x\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for leaf in LEAVES:
        assert runner.invoke(app, ["schedule", leaf, "x", "--help"]).exit_code == 0
    assert not (tmp_path / ".co" / "schedule-state.json").exists()
