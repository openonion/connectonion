"""
Purpose: One look for every `co` command's output: the palette, the layout of a result, progress, and when to print plain (#1997)
LLM-Note:
  Dependencies: imports from [os, sys, contextlib, rich.progress (only for a live bar or spinner)] | imported by [cli commands as they adopt it] | tested by [tests/unit/test_cli_style.py] | audited by [cli/audit.py style rules, black-box]
  Data flow: text → one role function (command, heading, ok, …) → a str, with ANSI when the stream is a colour terminal, the same words without it otherwise
  State/Effects: plain_output() sets a process-wide switch for --json; progress()/spinner() draw on stderr in a terminal and print milestone lines otherwise
  Integration: returns strings, so print(), typer.echo and logs all take them; the written standard is docs/cli/style.md and the cli-skill-design skill
  Errors: none raised; a stream without isatty() counts as not a terminal

The palette is the one the CLI already leaned on before it was written down:
cyan for what you can copy and run, bold for headings and numbers, green ✓,
yellow !, red ✗, dim for detail. Every function returns the same words in
both modes, which is what `co audit co --style` checks from the outside:
styled under a terminal, no escape codes under NO_COLOR or a pipe, and the
visible words identical.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

# SGR codes, not Rich markup: the result has to survive print(), typer.echo and
# a log file, and a Rich tag printed by any of those is a literal "[cyan]".
_SGR = {"command": "36", "path": "36", "heading": "1", "count": "1",
        "ok": "32", "warn": "33", "error": "31", "dim": "2"}

_PLAIN = False


def plain_output(on: bool = True) -> None:
    """Print plain for the rest of this process: a command calls it for --json."""
    global _PLAIN
    _PLAIN = on


def styled(stream=None) -> bool:
    """Whether output on `stream` (stdout by default) may carry colour.

    In order: --json (plain_output) and NO_COLOR always win; FORCE_COLOR asks
    for colour into a pipe; TERM=dumb is plain; otherwise only a terminal gets
    colour, so a pipe, a log file and launchd all get plain text.
    """
    if _PLAIN or os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    stream = sys.stdout if stream is None else stream
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def paint(role: str, text: str, stream=None) -> str:
    """`text` in the colour of `role` (a key of _SGR), or unchanged when plain."""
    text = str(text)
    return f"\033[{_SGR[role]}m{text}\033[0m" if text and styled(stream) else text


def command(cmd: str, stream=None) -> str:
    """A command someone can copy and run: `co rem status`."""
    return paint("command", cmd, stream)


def heading(text: str, stream=None) -> str:
    """The first line of a result, or a section's title."""
    return paint("heading", text, stream)


def dim(text: str, stream=None) -> str:
    """Detail that helps but is not the answer: a time, an id, a source."""
    return paint("dim", text, stream)


def ok(text: str, stream=None) -> str:
    """One line that worked or is healthy: `✓ Gmail connected`."""
    return f"{paint('ok', '✓', stream)} {text}"


def warn(text: str, stream=None) -> str:
    """One line that needs attention but did not fail: `! 3 pages are stale`."""
    return f"{paint('warn', '!', stream)} {text}"


def error(text: str, stream=None) -> str:
    """One line that failed: `✗ Outlook token expired`. Follow it with next_line()."""
    return f"{paint('error', '✗', stream)} {text}"


def count(n: int, unit: str, plural: str = "", stream=None) -> str:
    """`3 pages`, `1 page`: the number bold, the unit in words."""
    word = unit if n == 1 else (plural or unit + "s")
    return f"{paint('count', f'{n:,}', stream)} {word}"


def path(p, stream=None) -> str:
    """A file or folder, with the home directory written as ~ (shorter, and not private)."""
    text = str(p)
    home = str(Path.home())
    if text == home or text.startswith(home + os.sep):
        text = "~" + text[len(home):]
    return paint("path", text, stream)


def next_line(cmd: str, stream=None) -> str:
    """`Next: co rem status`: the label dim, the command in command colour.

    Next lines go to stderr (stdout stays data for --json), so the colour is
    decided for stderr unless a stream is given.
    """
    stream = sys.stderr if stream is None else stream
    return f"{dim('Next:', stream)} {command(cmd, stream)}"


def section(title: str, rows, stream=None) -> str:
    """A heading and one indented line per item; (label, value) pairs are aligned.

        Mail
          Gmail      ✓ connected, 2,113 messages
          Outlook    ✗ token expired
    """
    rows = list(rows)
    width = max((len(str(r[0])) for r in rows if isinstance(r, tuple)), default=0)
    lines = [heading(title, stream)]
    for row in rows:
        if isinstance(row, tuple):
            label, value = row
            lines.append(f"  {str(label).ljust(width)}   {value}")
        else:
            lines.append(f"  {row}")
    return "\n".join(lines)


class _Milestones:
    """Progress as plain lines: one at every tenth of the total, and the last."""

    def __init__(self, total: int, label: str, stream):
        self.total, self.label, self.stream, self.done, self._said = total, label, stream, 0, -1

    def advance(self, n: int = 1) -> None:
        self.done = min(self.total, self.done + n)
        step = self.done * 10 // self.total if self.total else 10
        if step > self._said:
            self._said = step
            print(f"{self.label}: {self.done}/{self.total}", file=self.stream, flush=True)


class _Bar:
    """A live Rich bar; advance() moves it."""

    def __init__(self, bar, task):
        self._bar, self._task = bar, task

    def advance(self, n: int = 1) -> None:
        self._bar.advance(self._task, n)


@contextmanager
def progress(total: int, label: str, stream=None):
    """Long work with a known total: a bar with n/total and elapsed time in a
    terminal, erased when done; plain milestone lines (`label: 12/40`) elsewhere,
    so a log or launchd still shows it is alive.

        with progress(len(people), "Reading mail") as bar:
            for person in people:
                read(person)
                bar.advance()
    """
    stream = sys.stderr if stream is None else stream
    if not styled(stream):
        yield _Milestones(total, label, stream)
        return
    from rich.console import Console
    from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=Console(file=stream, force_terminal=True), transient=True) as bar:
        yield _Bar(bar, bar.add_task(label, total=total))


@contextmanager
def spinner(label: str, stream=None):
    """Work with no known total: a spinner and elapsed time in a terminal,
    erased when done; nothing elsewhere. Print the result after it."""
    stream = sys.stderr if stream is None else stream
    if not styled(stream):
        yield
        return
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn(),
                  console=Console(file=stream, force_terminal=True), transient=True) as live:
        live.add_task(label, total=None)
        yield
