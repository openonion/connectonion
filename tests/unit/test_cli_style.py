"""Every role in connectonion/cli/style.py prints the same words styled and plain (#1997).

A command that adopts the module gets colour in a terminal and plain text in a
pipe, a log, launchd or --json without deciding anything itself. These tests
hold the one promise `co audit co --style` checks from the outside: strip the
escape codes from the styled output and it is the plain output, word for word.
"""

import io
import re

import pytest

from connectonion.cli import style

ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class Stream(io.StringIO):
    def __init__(self, terminal):
        super().__init__()
        self._terminal = terminal

    def isatty(self):
        return self._terminal


@pytest.fixture(autouse=True)
def _neutral_env(monkeypatch):
    for name in ("NO_COLOR", "FORCE_COLOR", "TERM"):
        monkeypatch.delenv(name, raising=False)
    yield
    style.plain_output(False)


def every_role(stream):
    return [
        style.command("co rem status", stream),
        style.heading("Notebook", stream),
        style.dim("updated 3 min ago", stream),
        style.ok("Gmail connected", stream),
        style.warn("3 pages are stale", stream),
        style.error("Outlook token expired", stream),
        style.count(2113, "message", stream=stream),
        style.path("/srv/notes", stream),
        style.next_line("co rem status", stream),
        style.section("Mail", [("Gmail", "connected"), ("Outlook", "expired"), "one more line"], stream),
    ]


def test_a_terminal_gets_colour_and_the_same_words_as_a_pipe():
    styled, plain = every_role(Stream(True)), every_role(Stream(False))
    assert all("\x1b[" in line for line in styled)
    assert not any("\x1b" in line for line in plain)
    assert [ESCAPE.sub("", line) for line in styled] == plain


def test_no_color_json_and_dumb_terminals_win_and_force_color_reaches_a_pipe(monkeypatch):
    terminal, pipe = Stream(True), Stream(False)
    monkeypatch.setenv("NO_COLOR", "1")
    assert not style.styled(terminal)
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.setenv("TERM", "dumb")
    assert not style.styled(terminal)
    monkeypatch.delenv("TERM")
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert style.styled(pipe)
    style.plain_output()          # what a command does for --json
    assert not style.styled(terminal)
    assert style.ok("done", terminal) == "✓ done"


def test_the_words_themselves():
    pipe = Stream(False)
    assert style.count(1, "page", stream=pipe) == "1 page"
    assert style.count(2113, "person", "people", pipe) == "2,113 people"
    assert style.error("Outlook token expired", pipe) == "✗ Outlook token expired"
    assert style.warn("stale", pipe) == "! stale"
    assert style.next_line("co auth", pipe) == "Next: co auth"
    assert style.section("Mail", [("Gmail", "✓ connected"), ("Outlook", "✗ expired")], pipe) == (
        "Mail\n  Gmail     ✓ connected\n  Outlook   ✗ expired")


def test_a_path_in_home_is_written_with_a_tilde():
    from pathlib import Path

    assert style.path(Path.home() / ".co" / "keys.env", Stream(False)) == "~/.co/keys.env"
    assert style.path("/etc/hosts", Stream(False)) == "/etc/hosts"


def test_progress_in_a_pipe_is_a_line_per_tenth_and_the_last():
    pipe = Stream(False)
    with style.progress(40, "Reading mail", pipe) as bar:
        for _ in range(40):
            bar.advance()
    lines = pipe.getvalue().splitlines()
    assert lines[-1] == "Reading mail: 40/40"
    assert len(lines) == 11
    assert "\x1b" not in pipe.getvalue()


def test_progress_and_spinner_in_a_terminal_draw_and_clean_up():
    terminal = Stream(True)
    with style.progress(3, "Reading mail", terminal) as bar:
        bar.advance(3)
    with style.spinner("Asking Gmail", terminal):
        pass
    assert "\x1b[" in terminal.getvalue()


def test_a_spinner_in_a_pipe_prints_nothing():
    pipe = Stream(False)
    with style.spinner("Asking Gmail", pipe):
        pass
    assert pipe.getvalue() == ""
