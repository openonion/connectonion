"""`co wechat` help, printed verbatim from wechat_help.md (#3355).

Typer's boxed layout hid the next step and cost an agent tokens on box drawing,
and had no room for when to run a command again (a key capture after migrating
chat history was nowhere). So each command prints its page as written, the way
`co rem` does: plain in a pipe, the same words styled in a terminal. A test holds
every page to the command's real options.
"""

import re
from functools import lru_cache
from pathlib import Path

import typer.core

SOURCE = Path(__file__).with_name("wechat_help.md")


@lru_cache(maxsize=1)
def pages() -> dict[str, str]:
    text = SOURCE.read_text(encoding="utf-8")
    return dict(re.findall(r"^## (co wechat[^\n]*)\n\n```\n(.*?)\n```", text, re.M | re.S))


def summary(name: str) -> str:
    """The one line `co commands` lists: the page's first sentence."""
    text = pages()[name].split(" — ", 1)[-1] if name == "co wechat" else pages()[name]
    first = " ".join(text.split("\n\n")[0].split())
    match = re.match(r"(.+?\.)(?:\s|$)", first)
    return match.group(1) if match else first


def verbatim(name: str, base=typer.core.TyperCommand):
    """A command (or group) class whose --help is exactly one page."""
    def format_help(self, ctx, formatter):
        from ..style import console
        text = pages()[name]
        if not console().is_terminal:
            formatter.write(text + "\n")
            return
        from . import rem_look
        rem_look.say(rem_look.page(text), plain=text, end="")

    def __init__(self, *args, **kwargs):
        base.__init__(self, *args, **kwargs)
        self.help = self.help if self.help and self.help != name else summary(name)
    return type("WechatHelp", (base,), {"format_help": format_help, "__init__": __init__})
