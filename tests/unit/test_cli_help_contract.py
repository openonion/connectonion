"""Every `co` command's help meets the #1643 contract, or is on a baseline that only shrinks (#1657, #1721).

The audit on 2026-09-25 found 300 commands and 14 that met the whole
contract. Failing CI on all of them at once would block every PR; checking
none is how the debt accumulated. So new commands must pass, and the
baseline records today's debt per check. A command that gets fixed has to
leave the baseline in the same PR, so the file can only get shorter.

Checked, deterministically and offline:
- `--help` exits 0 and writes nothing, under an empty HOME and cwd;
- a `Usage:` line, an `Example:` line, and a way back (`Back:` or `Next:`);
- whether it changes anything, said with one of LABELS;
- every `co …` it names in an Example, Next or Back line exists.

`co wiki` prints reviewed pages word for word and is held to them by
tests/e2e/cli/test_wiki_help_contract.py, so it is not checked twice here.
"""

import json
import re
from pathlib import Path

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.discovery import check, command_tree, commands_in
from connectonion.cli.main import app

BASELINE_PATH = Path(__file__).with_name("cli_help_baseline.json")
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
# The words a page uses to say what it changes. Fixed, so a reader and this
# test agree on what counts: "Read-only." or the verb for what it does.
LABELS = re.compile(r"\b(Read-only|Writes|Sends|Deletes|Removes|Creates|Changes|Charges|"
                    r"Deploys|Installs|Uploads|Publishes|Starts|Stops|Runs)\b")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
OWN_CONTRACT = ("co wiki",)
COMMANDS = [entry.path for entry in command_tree(app)
            if not entry.path.startswith(OWN_CONTRACT)]
runner = CliRunner()


def node(path):
    command = get_command(app)
    for word in path.split()[1:]:
        command = command.commands[word]
    return command


def failures(path, tmp_path, monkeypatch):
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(work)
    result = runner.invoke(app, [*path.split()[1:], "--help"], terminal_width=200)
    text = ANSI.sub("", result.stdout or "")
    command = node(path)
    said = f"{command.help or ''} {command.epilog or ''} {text}"
    found = set()
    if result.exit_code != 0:
        found.add("exit0")
    if any(home.iterdir()) or any(work.iterdir()):
        found.add("no_side_effect")
    if "Usage:" not in text and "co proxy" != path:
        found.add("usage")
    if not re.search(r"\bExamples?:", text):
        found.add("example")
    if not re.search(r"\b(Back|Next):", text):
        found.add("nav")
    if not LABELS.search(said):
        found.add("side_effect")
    for line in text.splitlines():
        if re.search(r"\b(Examples?|Next|Back):", line):
            for phrase in commands_in(line):
                if check(app, phrase):
                    found.add("refs")
    return found


@pytest.mark.parametrize("path", COMMANDS)
def test_help_meets_the_contract_or_is_on_the_baseline(path, tmp_path, monkeypatch):
    found = failures(path, tmp_path, monkeypatch)
    allowed = set(BASELINE.get(path, []))
    new = found - allowed
    assert not new, (
        f"`{path} --help` fails {sorted(new)}. See #1643 for the contract: an "
        f"Example: line, what it changes ({LABELS.pattern}), and a way back.")
    fixed = allowed - found
    assert not fixed, (
        f"`{path}` now passes {sorted(fixed)}: remove them from "
        f"{BASELINE_PATH.name} so the baseline cannot grow back.")


def test_the_baseline_names_only_commands_that_exist():
    stale = set(BASELINE) - set(COMMANDS)
    assert not stale, f"{BASELINE_PATH.name} lists commands that no longer exist: {sorted(stale)}"


def test_no_check_is_waived_that_every_page_can_already_pass():
    """exit0, no_side_effect, usage and refs pass everywhere today; they may never enter the baseline."""
    for path, checks in BASELINE.items():
        assert set(checks) <= {"example", "nav", "side_effect"}, (path, checks)
