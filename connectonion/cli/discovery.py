"""
Purpose: The register of every `co` command, read from the Typer app itself, so nothing that prints a command name can drift from what is registered.
LLM-Note:
  Dependencies: imports from [typer.main, re, dataclasses] | imported by [cli/main.py (bare `co` screen and `co commands`), tests/unit/test_cli_discovery.py, tests/unit/test_cli_tips_name_real_commands.py]
  Data flow: command_tree(app) → typer.main.get_command(app) → depth-first walk over every group's .commands → [Entry(path, summary, is_group)] | commands_in(text) → regex over prose → the `co …` phrases it names | check(app, phrase) → walks the phrase word by word through the tree → None when it is a command you can run, else the reason it is not
  State/Effects: none — reads the Typer app in memory; no I/O
  Integration: exposes command_tree(app), summary(cmd), commands_in(text), check(app, phrase) | the group/leaf rule in check(): at a group the next word must be a subcommand (or a flag, or the end); at a leaf anything may follow, because `co browser go_to <url>`, `co call <addr> …` and `co ai "…"` take their arguments positionally and Typer knows nothing about them
  Performance: get_command builds the Click tree once per call; the tree is ~180 nodes, so a walk is microseconds — callers do not cache
  Errors: check() returns a string rather than raising, so a sweep over many tips reports every bad one instead of stopping at the first
"""

import re
from dataclasses import dataclass
from typing import Iterator, List, Optional

import typer.main


@dataclass(frozen=True)
class Entry:
    path: str        # "co gmail read"
    summary: str     # first sentence of the help text
    is_group: bool   # True when it has subcommands of its own


def _children(cmd):
    """Subcommands of a Click group, or {} for a leaf.

    Duck-typed on purpose: typer 0.27 vendors its own Click (`typer._click`),
    so `isinstance(cmd, click.Group)` is False for every group in this CLI on
    exactly the version CI runs, and a walk written that way visits nothing.
    """
    return getattr(cmd, "commands", None) or {}


def summary(cmd) -> str:
    """The first sentence of a command's help, as the register prints it.

    Docstrings here run to several lines; the first sentence is the line a
    listing can carry. Cut at the first period that ends a sentence, not at a
    fixed width, so a summary is never a half word.
    """
    text = (cmd.help or "").strip()
    first_line = text.splitlines()[0] if text else ""
    match = re.match(r"(.+?\.)(?:\s|$)", first_line)
    return match.group(1) if match else first_line


def command_tree(app: typer.Typer) -> List[Entry]:
    """Every command reachable from `co`, depth-first, in registration order
    (the order `--help` prints them), each with its summary."""
    root = typer.main.get_command(app)

    def walk(cmd, path: List[str]) -> Iterator[Entry]:
        for name, child in _children(cmd).items():
            if child.hidden:
                # There are none today, and a test keeps it so — a hidden
                # command is one an agent can only reach by guessing.
                continue
            here = path + [name]
            yield Entry(" ".join(here), summary(child), bool(_children(child)))
            yield from walk(child, here)

    return list(walk(root, ["co"]))


# A `co` phrase: the word `co` followed by one or more command-shaped words.
# Stops at anything that is not a lowercase word — `<#>`, `{name}`, `--flag`,
# a number, a quote — so the phrase is exactly the part that has to exist.
# `\bco ` does not match `co-ai`, `co/gemini`, or the tail of `Cisco`.
_PHRASE = re.compile(r"\bco((?: [a-z][a-z0-9-]*)+)")


def commands_in(text: str) -> List[str]:
    """The `co …` phrases a piece of prose names, e.g. a tip."""
    return ["co" + m.group(1) for m in _PHRASE.finditer(text)]


def check(app: typer.Typer, phrase: str) -> Optional[str]:
    """None if `phrase` is a command you can run; otherwise why it is not.

    At a group, the next word must be one of its subcommands. At a leaf,
    anything may follow: `co browser tab ls` is fine because `browser` is a
    leaf that parses its own arguments. This is what lets the sweep flag
    `co gmail open 1` (gmail is a group, open is not in it) without flagging
    `co browser go_to x.com`.
    """
    words = phrase.split()
    if words[:1] != ["co"]:
        return f"{phrase!r} does not start with `co`"
    node = typer.main.get_command(app)
    for i, word in enumerate(words[1:], start=1):
        children = _children(node)
        if not children:
            return None                       # a leaf: the rest is its own arguments
        if word.startswith("-"):
            return None                       # a flag on the group itself
        if word not in children:
            here = " ".join(words[:i])
            return (f"`{here}` has no subcommand `{word}` "
                    f"(it has: {', '.join(sorted(children))})")
        node = children[word]
    return None
