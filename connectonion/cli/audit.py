"""
Purpose: Check that every `co` command's help is something an agent can act on (#1643, #1735)
LLM-Note:
  Dependencies: imports from [typer, cli/discovery.py, cli/commands/command_tips.py, core/usage.py, llm_do] | imported by [cli/commands/audit_commands.py, tests/unit/test_cli_help_contract.py, tests/e2e/real_api/test_cli_discovery_journeys.py]
  Data flow: command_tree(app) → help_page(path) in an empty HOME and cwd → check_page() findings | discover(path) → a text-only model walks help pages from `co --help` and names one command
  State/Effects: none outside a temporary sandbox; discover() calls a model
  Integration: one engine for the `co audit` command and for CI, so the command and the tests cannot disagree
  Errors: a finding names the check that failed and the fix; nothing is raised for a bad page

Hard rules first, then judgement, as the maintainer set it out:

- audit(): every rule a regex or the command tree can decide. Each page exits
  0 and writes nothing, has Usage, an Example that invokes this command with
  flags it has, says what it changes, names its way back and leaks no private
  path or address; and every group's page lists all of its children. Since
  `co --help` is a group page, that last rule means every command can be
  reached by following printed names from the top. Free, deterministic,
  offline.
- review(): only for pages that pass every rule, a model judges what needs
  judgement: is the purpose clear to a newcomer, does "what it changes" match
  the command, is the example realistic, is the page simple.
"""

import functools
import hashlib
import os
import re
import shlex
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field
from typer.main import get_command
from typer.testing import CliRunner

from .discovery import check, command_tree, commands_in

# The words a page uses to say what it changes. Fixed, so a reader and this
# check agree on what counts: "Read-only." or the verb for what it does.
LABELS = re.compile(r"\b(Read-only|Writes|Sends|Deletes|Removes|Creates|Changes|Charges|"
                    r"Deploys|Installs|Uploads|Publishes|Starts|Stops|Runs)\b")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
# `co wiki` prints reviewed pages word for word, held to them by
# tests/e2e/cli/test_wiki_help_contract.py.
OWN_CONTRACT = ("co wiki",)
# Pages written by hand rather than by Typer, so they have no `Usage:` line.
HAND_WRITTEN = {"co proxy"}
FIXES = {
    "exit0": "`--help` must exit 0; it failed here",
    "writes": "`--help` wrote a file; help must not load credentials or create state",
    "usage": "no `Usage:` line",
    "example": 'add epilog="Example:  co … <placeholder>" with flags that exist',
    "side_effect": "say what it changes with one of: " + LABELS.pattern.strip("\\b()").replace("|", ", "),
    "back": "no `Back:` line; name_the_way_back() adds it unless the page is hand-written",
    "refs": "an Example, Next or Back line names a command that does not exist",
    "flags": "an Example uses a flag this command does not have",
    "lists_children": "the group page does not list every subcommand, so a reader cannot reach it",
    "self_example": "no Example invokes this command itself",
    "private": "an Example contains a real home path or a full 0x address; use a placeholder",
    "review": "a model reviewer flagged this page",
}
# A real home directory or a full 40-hex address in an example is someone's
# data, not a placeholder. Narrow on purpose: NAS paths and chat ids are fine.
PRIVATE = re.compile(r"/Users/[a-z][\w.-]*/|\b0x[0-9a-fA-F]{40}\b")



@dataclass(frozen=True)
class Finding:
    path: str
    check: str
    detail: str = ""

    @property
    def fix(self) -> str:
        return FIXES[self.check] + (f": {self.detail}" if self.detail else "")


def commands(app, prefix: str = "co") -> list:
    """Every command at or under `prefix`, outside the pages with their own contract."""
    return [e.path for e in command_tree(app)
            if (e.path == prefix or e.path.startswith(prefix + " ") or prefix == "co")
            and not e.path.startswith(OWN_CONTRACT)]


@functools.lru_cache(maxsize=8)
def _tree(app):
    """The built command tree, once per app: building it is most of an audit's time."""
    return get_command(app)


def node(app, path: str):
    command = _tree(app)
    for word in path.split()[1:]:
        command = command.commands[word]
    return command


@contextmanager
def _sandbox():
    """An empty HOME and cwd, so reading help cannot see or touch real state."""
    home, work = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    old_home, old_cwd = os.environ.get("HOME"), os.getcwd()
    os.environ["HOME"] = str(home)
    os.chdir(work)
    try:
        yield home, work
    finally:
        os.chdir(old_cwd)
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home


def help_page(app, path: str) -> tuple:
    """(exit code, page text without colour, whether reading it wrote a file)."""
    with _sandbox() as (home, work):
        result = CliRunner().invoke(app, [*path.split()[1:], "--help"], terminal_width=200)
        wrote = any(home.iterdir()) or any(work.iterdir())
    return result.exit_code, ANSI.sub("", result.stdout or ""), wrote


def _example_commands(text: str):
    """Each `co …` invocation an Example line shows, as a word list."""
    for line in text.splitlines():
        if re.search(r"\bExamples?:", line):
            for part in re.split(r"\s\|\s", line.split(":", 1)[1]):
                part = part.strip().strip("│").strip()
                if part.startswith("co ") and part.count('"') % 2 == 0:
                    yield shlex.split(part.replace("\\", ""))


def _invoked(app, words: list) -> str:
    """The command an example runs: follow subcommand names, skip options and their values."""
    command, path = _tree(app), ["co"]
    for word in words[1:]:
        children = getattr(command, "commands", None) or {}
        if word in children:
            command, path = children[word], path + [word]
    return " ".join(path)


def _unknown_flags(app, words: list) -> list:
    """Flags in one example that no command on its path accepts."""
    command, options = _tree(app), {"--help"}
    for word in words[1:]:
        options |= {opt for param in command.params for opt in (*param.opts, *param.secondary_opts)}
        children = getattr(command, "commands", None) or {}
        if word in children:
            command = children[word]
    options |= {opt for param in command.params for opt in (*param.opts, *param.secondary_opts)}
    return [w for w in words if w.startswith("--") and w.split("=")[0] not in options]


def check_page(app, path: str) -> list:
    """Layers 1 and 3 for one command: what is wrong with its page."""
    code, text, wrote = help_page(app, path)
    command = node(app, path)
    said = f"{command.help or ''} {command.epilog or ''} {text}"
    found = []

    def add(check_name, detail=""):
        found.append(Finding(path, check_name, detail))

    if code != 0:
        add("exit0")
    if wrote:
        add("writes")
    if "Usage:" not in text and path not in HAND_WRITTEN:
        add("usage")
    if not re.search(r"\bExamples?:", text):
        add("example")
    if not re.search(r"\b(Back|Next):", text):
        add("back")
    if not LABELS.search(said):
        add("side_effect")
    for line in text.splitlines():
        if re.search(r"\b(Examples?|Next|Back):", line):
            for phrase in commands_in(line):
                reason = check(_tree(app), phrase)
                if reason:
                    add("refs", reason)
    # A command that parses its own arguments (`co browser`, `co proxy`) has
    # flags Typer never sees, so they cannot be checked from the registration.
    parses_own = (command.context_settings or {}).get("ignore_unknown_options")
    examples = list(_example_commands(text))
    for words in [] if parses_own else examples:
        bad = _unknown_flags(app, words)
        if bad:
            add("flags", f"{' '.join(bad)} in `{' '.join(words)}`")
    ran = [_invoked(app, words) for words in examples]
    if examples and not any(r == path or r.startswith(path + " ") for r in ran):
        add("self_example", f"examples run {', '.join(sorted(set(ran)))}")
    for line in text.splitlines():
        if re.search(r"\bExamples?:", line) and PRIVATE.search(line):
            add("private", PRIVATE.search(line).group())
    children = [name for name, child in (getattr(command, "commands", None) or {}).items() if not child.hidden]
    missing = [name for name in children if not re.search(rf"(^|[\s│]){re.escape(name)}\s", text, re.M)]
    if missing:
        add("lists_children", ", ".join(missing))
    return found


def audit(app, prefix: str = "co") -> list:
    """Every hard rule for every command under `prefix`. Free and deterministic."""
    return [finding for path in commands(app, prefix) for finding in check_page(app, path)]


def inventory(app) -> dict:
    """Each command's help, fingerprinted, so a later run can audit only what changed."""
    return {path: hashlib.sha256(help_page(app, path)[1].encode()).hexdigest()[:16]
            for path in commands(app)}


def changed_since(app, base: dict) -> list:
    """Commands added since `base`, or whose help text changed."""
    return [path for path, digest in inventory(app).items() if base.get(path) != digest]


PROMPT = """You operate a CLI named `co` and can only read its help pages. Goal: {goal}
Pages you have read so far:
{pages}
Reply with exactly one line:
HELP <command path>   to read that command's --help (e.g. HELP co gmail), or
RUN <full command>    when you know the command that achieves the goal."""


def walk(app, goal: str, model: str, max_pages: int = 8) -> tuple:
    """A text-only model reads help pages from `co --help` until it names one command.

    Returns (the command it named or None, the pages it read). Pages are never
    truncated: a first version cut them at 6,000 characters and hid half of
    `co --help`, and four "failures" were the harness's own.
    """
    from connectonion import llm_do

    pages = {"co": help_page(app, "co")[1]}
    for _ in range(max_pages):
        read = "\n\n".join(f"$ {path} --help\n{text}" for path, text in pages.items())
        reply = str(llm_do(PROMPT.format(goal=goal, pages=read), model=model)).strip()
        reply = reply.splitlines()[0].strip("` ") if reply else ""
        if reply.startswith("HELP "):
            path = reply[5:].strip()
            path = path if path.startswith("co") else f"co {path}"
            code, text, _ = help_page(app, path)
            pages[path] = text if code == 0 else f"(no such command: {path})"
            continue
        return (reply.removeprefix("RUN ").strip() or None), list(pages)
    return None, list(pages)


class Review(BaseModel):
    """What a reviewer says about one help page."""
    clear: bool = Field(description="a newcomer knows when to use this command, from the first line")
    effects_match: bool = Field(description="what the page says it changes matches what the command name and options imply")
    example_realistic: bool = Field(description="the example is one a user would actually run")
    simple: bool = Field(description="short, plain words, no internal jargon or issue numbers needed to understand it")
    suggestion: str = Field(description="one concrete rewrite of the weakest sentence, or empty if all pass")


REVIEW_PROMPT = """You review one help page of a CLI named `co`. Its readers are people
and AI agents deciding whether and how to run the command. Judge only this page.

$ {path} --help
{page}"""


def review(app, path: str, model: str):
    """A Finding when a model judges the page unclear, inaccurate, unrealistic or not simple.

    Run it after audit(): hard rules are cheaper and certain, and a page that
    fails one is not worth a model's opinion yet.
    """
    from connectonion import llm_do

    page = help_page(app, path)[1]
    verdict = llm_do(REVIEW_PROMPT.format(path=path, page=page), output=Review, model=model)
    failed = [name for name in ("clear", "effects_match", "example_realistic", "simple")
              if not getattr(verdict, name)]
    if not failed:
        return None
    return Finding(path, "review", f"{', '.join(failed)}; {verdict.suggestion}")
