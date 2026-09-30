"""One look for every co command (#1997).

A command's result used to look like whatever its author printed: Rich panels
in `co status`, bare `key: value` dumps in `co rem status`, plain text almost
everywhere else, and nothing marked the command to run next. This module is
the palette and the few shapes every command uses, so the same thing looks the
same wherever it appears:

- a command a person can run (examples, Next lines) is `command`;
- a number that matters is `count`; a filesystem path is `path`;
- a warning is `warn`, an error `error`, a section title `heading`;
- a finished good state is `ok`, secondary detail `muted`.

Plain when it should be plain. Rich already turns colour off for NO_COLOR,
TERM=dumb and anything that is not a terminal (a pipe, a log, launchd), and
on for FORCE_COLOR; every helper goes through it, so the words are identical
either way and only the styling differs. `--json` output never passes through
here.

Usage:
    from connectonion.cli.style import console, next_line, command, count
    out = console()
    out.print(f"Mapped {count(312)} people. Open them with {command('co rem open')}.")
    out.print(next_line("co rem start"))
"""

from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.theme import Theme

THEME = Theme({
    "co.command": "bold cyan",
    "co.next": "bold",
    "co.count": "bold",
    "co.path": "dim",
    "co.warn": "yellow",
    "co.error": "bold red",
    "co.heading": "bold underline",
    "co.ok": "green",
    "co.muted": "dim",
})


def console(stderr: bool = False) -> Console:
    """The console every co command prints through. Colour follows the terminal, NO_COLOR and FORCE_COLOR."""
    return Console(theme=THEME, stderr=stderr, highlight=False, soft_wrap=True)


def _wrap(style: str, text) -> str:
    return f"[{style}]{escape(str(text))}[/{style}]"


def command(text: str) -> str:
    return _wrap("co.command", text)


def count(value) -> str:
    return _wrap("co.count", value)


def path(value) -> str:
    return _wrap("co.path", value)


def warn(text: str) -> str:
    return _wrap("co.warn", text)


def error(text: str) -> str:
    return _wrap("co.error", text)


def heading(text: str) -> str:
    return _wrap("co.heading", text)


def ok(text: str) -> str:
    return _wrap("co.ok", text)


def muted(text: str) -> str:
    return _wrap("co.muted", text)


def next_line(cmd: str) -> str:
    """`Next: <command>`, the one line every result ends with."""
    return f"[co.next]Next:[/co.next] {command(cmd)}"


def progress(out: Console = None) -> Progress:
    """Progress for long work: a bar with i/N when the total is known, a spinner with elapsed time when not.

    Add a task with `total=None` for a spinner. Nothing is drawn when the
    console is not a terminal, so pipes and logs see only the lines the
    command prints itself.
    """
    out = out or console(stderr=True)
    # Off a terminal Rich still prints the last frame when the bar stops (an
    # empty line when disabled), so the bar gets a console that prints nothing.
    shown = out if out.is_terminal else Console(quiet=True)
    return Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(),
                    TimeElapsedColumn(), console=shown, transient=True)
