"""`co wiki` help, printed verbatim from wiki_help.md.

The help pages are the design (#1656): they were agreed first, and the code
follows them. Generated help reflowed every page -- the Usage and Example
columns ran together, and a flag with no help string printed nothing at all,
which is how `reflect --basis` and `review --verdict` reached users with no
explanation. So each command prints its page as written, and a test holds the
page to the command's real options.
"""

import os
import re
from functools import lru_cache
from pathlib import Path

import typer.core

SOURCE = Path(__file__).with_name("wiki_help.md")


@lru_cache(maxsize=1)
def pages() -> dict[str, str]:
    text = SOURCE.read_text(encoding="utf-8")
    return dict(re.findall(r"^## (co wiki[^\n]*)\n\n```\n(.*?)\n```", text, re.M | re.S))


def page(name: str) -> str:
    """One page, spelled for the program that invoked it (a wrapper names itself)."""
    text = pages()[name]
    program = os.environ.get("CO_WIKI_PROGRAM") or "co wiki"
    return text if program == "co wiki" else text.replace("co wiki", program)


def verbatim(name: str, base=typer.core.TyperCommand):
    """A command (or group) class whose --help is exactly one page."""
    def format_help(self, ctx, formatter):
        formatter.write(page(name) + "\n")
    return type("WikiHelp", (base,), {"format_help": format_help})
