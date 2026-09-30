"""`co rem` looks like every co command in a terminal and prints the same words anywhere else (#1996).

The rule `co audit`'s `look` check applies (#1997), held here on its own:
(a) in a colour terminal the page is styled; (b) with NO_COLOR, TERM=dumb and a
pipe it carries no escape codes at all; (c) the words of (a), escapes
stripped, are the words of (b). Every `co rem` help page is walked from the
command tree, so a page added later is held to it without editing this file;
`co rem status` and bare `co rem` run in an empty HOME as a real process.
"""

import os
import re
import subprocess
import sys

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.main import app

runner = CliRunner()
ESCAPE = re.compile(r"\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\))")
SGR = re.compile(r"\x1b\[[0-9;]*m")
STYLED = {"FORCE_COLOR": "1", "TERM": "xterm-256color", "COLUMNS": "100", "NO_COLOR": None}
PLAIN = {"NO_COLOR": "1", "TERM": "dumb", "FORCE_COLOR": None, "COLUMNS": None}


def words(text):
    """Word tokens, ignoring whitespace and box drawing, the way the audit compares them."""
    return re.findall(r"[^\s─-╿]+", ESCAPE.sub("", text))


def pages(command=get_command(app).commands["rem"], path=()):
    yield path
    for name, sub in getattr(command, "commands", {}).items():
        yield from pages(sub, (*path, name))


def looks_right(styled, plain):
    assert SGR.search(styled), "no styling in a colour terminal"
    assert "\x1b" not in plain, "escape codes with NO_COLOR, TERM=dumb and a pipe"
    assert words(styled) == words(plain)


@pytest.mark.parametrize("path", list(pages()), ids=lambda path: " ".join(["co rem", *path]))
def test_every_help_page_is_styled_in_a_terminal_and_the_same_words_without(path):
    args = ["rem", *path, "--help"]
    styled = runner.invoke(app, args, env=STYLED)
    plain = runner.invoke(app, args, env=PLAIN)
    assert styled.exit_code == plain.exit_code == 0, plain.output
    looks_right(styled.output, plain.output)


@pytest.mark.parametrize("args", [["status"], [], ["--help"]], ids=["status", "bare", "help"])
def test_a_real_process_in_an_empty_home_passes_the_look_rule(tmp_path, args):
    def run(extra):
        env = {**os.environ, "HOME": str(tmp_path), **extra}
        env = {key: value for key, value in env.items() if value is not None}
        done = subprocess.run([sys.executable, "-m", "connectonion.cli.main", "rem", *args],
                              capture_output=True, text=True, timeout=60, env=env)
        assert done.returncode == 0, done.stderr
        return done.stdout

    looks_right(run(STYLED), run(PLAIN))
    assert not (tmp_path / ".co" / "rem").exists(), "looking wrote a notebook"
