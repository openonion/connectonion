"""`co rem` help, printed verbatim from rem_help.md.

The help pages are the design (#1656): they were agreed first, and the code
follows them. Generated help reflowed every page -- the Usage and Example
columns ran together, and a flag with no help string printed nothing at all,
which is how `reflect --basis` and `review --verdict` reached users with no
explanation. So each command prints its page as written, and a test holds the
page to the command's real options. A terminal sees the same words in the
shared palette (#1996): headings, the command column and every `co rem ...`.
"""

import re
from functools import lru_cache
from pathlib import Path

import typer.core

SOURCE = Path(__file__).with_name("rem_help.md")


@lru_cache(maxsize=1)
def pages() -> dict[str, str]:
    text = SOURCE.read_text(encoding="utf-8")
    return dict(re.findall(r"^## (co rem[^\n]*)\n\n```\n(.*?)\n```", text, re.M | re.S))


def page(name: str) -> str:
    """One page, spelled for the program that invoked it (a wrapper names itself)."""
    text = pages()[name]
    from ...rem.migrate import program
    program = program()
    return text if program == "co rem" else text.replace("co rem", program)


def summary(name: str) -> str:
    """The one line `co commands` lists for this page, taken from the pages.

    A command listed on the root or advanced page is summarised by that line,
    so the listing and the page cannot disagree; any other page by its first
    sentence.
    """
    word = name.split()[-1]
    for listing in ("co rem", "co rem advanced"):
        found = re.search(rf"^  {re.escape(word)}\s{{2,}}(.+)$", pages()[listing], re.M)
        if found and len(name.split()) == 3:
            return found.group(1).strip()
    text = pages()[name].split(" — ", 1)[-1] if name == "co rem" else pages()[name]
    first = " ".join(text.split("\n\n")[0].split())
    match = re.match(r"(.+?\.)(?:\s|$)", first)
    return match.group(1) if match else first


def show(name: str, end: str = "\n") -> None:
    """Print one page: styled in a terminal, word for word as written anywhere else."""
    from . import rem_look
    text = page(name)
    rem_look.say(rem_look.page(text), plain=text, end=end)


def verbatim(name: str, base=typer.core.TyperCommand):
    """A command (or group) class whose --help is exactly one page."""
    def format_help(self, ctx, formatter):
        from ..style import console
        if not console().is_terminal:
            formatter.write(page(name) + "\n")
            return
        # Click prints what the formatter holds and then a newline; a styled
        # page is printed here instead, so the newline ends it the same way.
        show(name, end="")

    def __init__(self, *args, **kwargs):
        base.__init__(self, *args, **kwargs)
        self.help = self.help if self.help and self.help != name else summary(name)
    return type("RemHelp", (base,), {"format_help": format_help, "__init__": __init__})
