"""How co rem text looks in a terminal: the shared palette on co rem's own words (#1996).

co rem printed plain text everywhere: help pages, results, the Next line. The
words are right and tests hold them; what a terminal lacked was the look every
co command shares (connectonion/cli/style.py). This module adds it without
touching a word: each line is read for what is in it -- a `co rem ...` command
someone can type, a section title, a path, a count, a warning -- and marked
up with the palette. In a terminal that markup is printed; anywhere else (a
pipe, a log, launchd, NO_COLOR, TERM=dumb) the plain words are, exactly as
before, so nothing machine-read changes. `--json` never comes here.
"""

import re
from functools import lru_cache

import typer
from rich.markup import escape
from rich.text import Text

from .. import style

# Words that continue a command after `co rem`: its commands and subcommands
# (from the help pages) and the arguments pages name. A lowercase word outside
# them ends the phrase, so "until co rem start is approved" marks only the command.
ARGUMENTS = {"me", "people", "projects", "orgs", "skills", "all", "gmail", "outlook", "codex",
             "claude-code", "whatsapp", "google", "microsoft", "login", "decisions", "notes"}
TOKEN = (r"~?[\w.+-]*[/@][\w./@+,-]*\w|--?[a-z][\w-]*(?:=[^\s,;)]+)?|[A-Z][A-Z_]*(?:\.\.\.)?|\"[^\"\n]*\""
         r"|\[[^\]\n]*\]|<[^>\s]+>|\d+[a-z]*|\.\.\.")
PATH = r"(?<![\w/.])(?:~/|/(?=[\w.]))[^\s,;()'\"`]*[\w/]"
COUNT = r"(?<![\w./:-])\d[\d,]*(?![\w/:-]|\.\d)"


def _commands() -> re.Pattern:
    from ...rem.migrate import program
    return _pattern(program())


@lru_cache(maxsize=4)
def _pattern(program: str) -> re.Pattern:
    from .rem_help import pages
    words = {word for name in pages() for word in name.split()[2:]} | ARGUMENTS
    word = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    programs = "|".join(re.escape(p) for p in sorted({program, "co rem", "co auth"}, key=len, reverse=True))
    token = rf"(?:{TOKEN}|(?:{word})(?![\w/-]))"
    return re.compile(rf"(?<![\w-])(?:{programs})(?: {token})*(?![\w-])")


def highlight(line: str, *, counts: bool = False) -> str:
    """One plain line as markup: commands, paths and (in results) counts styled; every other word as written."""
    spans = [(m.start(), m.end(), style.command) for m in _commands().finditer(line)]
    spans += [(m.start(), m.end(), style.path) for m in re.finditer(PATH, line)]
    if counts:
        spans += [(m.start(), m.end(), style.count) for m in re.finditer(COUNT, line)]
    out, at = [], 0
    for start, end, paint in sorted(spans, key=lambda span: span[:2]):
        if start < at:
            continue  # inside a command already: `co rem show people/a.md` is one command, not a command and a path
        out += [_literal(line[at:start], before_tag=True), paint(line[start:end])]
        at = end
    return "".join(out) + _literal(line[at:], before_tag=False)


def _literal(text: str, *, before_tag: bool) -> str:
    """Markup for text exactly as written. Rich reads backslashes only before a
    tag, so a trailing run is doubled there and left alone at a line's end
    (`co rem reflect ... \\` continues on the next line)."""
    stem = text.rstrip("\\")
    tail = text[len(stem):]
    return escape(stem) + (tail * 2 if before_tag else tail)


# The console a spinner is drawing on (rem_output.Turn), while one is. A line
# printed on another console landed on the spinner's own row: "gmail: to
# 2026-09-17, 40 mails" over "Writing your page… 0:41" (#2008).
LIVE = None


def say(markup: str, *, err: bool = False, plain: str = None, end: str = "\n") -> None:
    """Print markup in a terminal; elsewhere the same words, plain, through typer as before."""
    out = LIVE if err and LIVE is not None else style.console(stderr=err)
    if out.is_terminal:
        out.print(markup, emoji=False, end=end)
    else:
        typer.echo(Text.from_markup(markup, emoji=False).plain if plain is None else plain, err=err, nl=end == "\n")


def result(text: str, *, titled: bool = True) -> str:
    """A result as `render` wrote it: its title a heading, errors and warnings marked, commands styled."""
    lines, marked = text.split("\n"), []
    if titled:
        head, attention, _ = lines.pop(0).partition(" — needs attention")
        marked.append(style.heading(head) + (" — " + style.error("needs attention") if attention else ""))
    return "\n".join([*marked, *(_result_line(line) for line in lines)])


def line(text: str, *, err: bool = False) -> None:
    """Print one plain line of progress or outcome (`[2/5] people/a.md`, `Stopped: ...`) in the palette."""
    say(_result_line(text), err=err, plain=text)


def _result_line(text: str) -> str:
    label = re.match(r"(\s*)(Error|Warning|Stopped):(?= |$)", text)
    if not label:
        return highlight(text, counts=True)
    paint = style.error if label.group(2) == "Error" else style.warn
    return label.group(1) + paint(label.group(2) + ":") + highlight(text[label.end():], counts=True)


def page(text: str) -> str:
    """A help page as markup: section titles as headings, the command column and every command styled."""
    lines = text.split("\n")
    return "\n".join(_page_line(line, lines[number + 1] if number + 1 < len(lines) else "", number)
                     for number, line in enumerate(lines))


def _page_line(line: str, following: str, number: int) -> str:
    label = re.match(r"([A-Z][\w ]*(?:\([^)\n]*\))?:)(?=\s|$)", line)
    if label and number and len(label.group(1).split()) <= 5:
        return style.heading(label.group(1)) + _page_rest(line[label.end():])
    if (number and re.fullmatch(r"[A-Z][\w ]*(?: \([\w ]+\))?", line) and len(line.split()) <= 4
            and following.startswith("  ")):
        return style.heading(line)   # "Build (once)", "Read", "Keep it current"
    column = re.match(r"(  +)([a-z][a-z-]*|--?[a-z][\w-]*(?: [A-Z][\w.,\[\]|-]*)?)(?=\s{2,}|$)", line)
    if column:
        return column.group(1) + style.command(column.group(2)) + _page_rest(line[column.end():])
    return highlight(line)


def _page_rest(text: str) -> str:
    """The text after a label: an option column (`--root DIR`) keeps its option styled."""
    option = re.match(r"(\s+)(--[a-z][\w-]*)(?=\s)", text)
    if option and not _commands().match(text.lstrip()):
        return option.group(1) + style.command(option.group(2)) + highlight(text[option.end():])
    return highlight(text)
