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

A page written as one string rather than built by Typer (`co proxy`) goes
through `markup`, which colours what it can find without changing a word.
"""

import re

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
    # A dashboard's section label (`Today`, `Mailboxes`): bold, not underlined,
    # so the one underlined heading is the title (1.9.0a9).
    "co.label": "bold",
    # Rich's own progress colours were pink, green and yellow on one line; a
    # bar is the accent (the green of a finished state) on a dim track, its
    # count bold like every count, its elapsed time dim (1.9.0a9).
    "bar.complete": "green",
    "bar.finished": "green",
    "bar.pulse": "green",
    "bar.back": "dim",
    "progress.spinner": "green",
    "progress.download": "bold",
    "progress.elapsed": "dim",
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


def label(text: str) -> str:
    return _wrap("co.label", text)


def next_line(cmd: str) -> str:
    """`Next: <command>`, the one line every result ends with."""
    return f"[co.next]Next:[/co.next] {command(cmd)}"


# A `co …` command in text written as one string: at the start of a line,
# after a label's `: `, a `| ` or a backtick, and up to two spaces, ` — `, a
# closing backtick or bracket, ` (` opening a parenthetical, or the end of the
# line. Prose that merely uses the word is not found in the middle of a
# sentence, and `cobalt` never is. Without ` (`, "Next: co status (balance and
# deployments; …)" was coloured as one long command (#2008).
_COMMAND = re.compile(r"(^[ \t]*|(?<=: )|(?<=:  )|(?<=\| )|(?<=`))(co(?: (?!— )[^\s`)]+)*?)(?=  | — | \(|[`)]|$)")
_HEADING = re.compile(r"[A-Z][A-Za-z ]*:")
_NEXT = re.compile(r"(\s*)Next: (.*)")


def _commands(line: str) -> str:
    out, last = "", 0
    for found in _COMMAND.finditer(line):
        out += escape(line[last:found.start(2)]) + command(found.group(2))
        last = found.end(2)
    return out + escape(line[last:])


def _line(line: str) -> str:
    if _HEADING.fullmatch(line):
        return heading(line)
    shown = _NEXT.fullmatch(line)
    if shown:   # next_line's shape, with or without a few words before the command
        return f"{shown.group(1)}[co.next]Next:[/co.next] {_commands(shown.group(2))}"
    return _commands(line)


def markup(text: str) -> str:
    """Text written as one string (a hand-written help page, a tip) in the palette, word for word.

    Each command it shows is a `command`, an `Options:`-style title a
    `heading`, and a `Next:` line has next_line's shape.
    """
    return "\n".join(_line(line) for line in text.split("\n"))


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
    return Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(bar_width=24), MofNCompleteColumn(),
                    TimeElapsedColumn(), console=shown, transient=True)
