"""
Purpose: Check that every `co` command's help is something an agent can act on, by running `co` and reading only what it prints (#1643, #1735)
LLM-Note:
  Dependencies: imports from [subprocess, concurrent.futures, pydantic, llm_do] | imported by [cli/commands/audit_commands.py, tests/unit/test_cli_help_contract.py, tests/unit/test_co_audit_rules.py, tests/e2e/real_api/test_cli_discovery_journeys.py]
  Data flow: help_page(words) runs `co <words> --help` → pages() walks every name printed from `co --help` down → check() rules on each page's text | unreachable() = `co commands` minus what the walk found | review() → a model judges one page
  State/Effects: runs `co` in a fresh empty HOME and cwd per page; review() calls a model
  Integration: one engine for `co audit` and for CI | knows nothing of the source: an agent only ever sees output, and neither does this
  Errors: a finding names the rule and the fix; a page that fails to print is itself a finding

Hard rules first, then judgement, as the maintainer set it out. Every rule is
decided from printed output alone, the way an agent meets the CLI:

- pages(): start at `co --help`, open every command a page lists, repeat. What
  this walk cannot reach, an agent cannot either; unreachable() compares it
  with the full register `co commands` prints.
- check(): per page, it prints and exits 0, writes nothing, has Usage, an
  Example that runs this command with flags the page documents, says what it
  changes, names its way back, and leaks no private path or address.
- review(): only for pages that pass, a model judges what needs judgement:
  clear, accurate, a realistic example, simple.
"""

import hashlib
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

# The words a page uses to say what it changes. Fixed, so a reader and this
# check agree on what counts: "Read-only." or the verb for what it does.
LABELS = re.compile(r"\b(Read-only|Writes|Sends|Deletes|Removes|Creates|Changes|Charges|"
                    r"Deploys|Installs|Uploads|Publishes|Starts|Stops|Runs)\b")
# A command as a page lists it: `│ name   summary` (Typer) or `  name   summary`.
LISTED = re.compile(r"^(?:│ |  )([a-z][a-z0-9_-]*)\s{2,}\S", re.M)
# A command as `co commands` lists it: the path, then the summary.
REGISTERED = re.compile(r"^(co(?: [a-z][a-z0-9_-]*)*)(?:\s{2,}|$)", re.M)
# A real home directory or a full 40-hex address in an example is someone's
# data, not a placeholder. Narrow on purpose: NAS paths and chat ids are fine.
PRIVATE = re.compile(r"/Users/[a-z][\w.-]*/|\b0x[0-9a-fA-F]{40}\b")
PHRASE = re.compile(r"\bco((?: [a-z][a-z0-9_-]*)+)")
# `co wiki` prints reviewed pages word for word, held to them by
# tests/e2e/cli/test_wiki_help_contract.py; it is walked but not re-checked.
OWN_CONTRACT = "co wiki"
FIXES = {
    "exit0": "`--help` must print and exit 0",
    "writes": "`--help` wrote a file; help must not load credentials or create state",
    "usage": "no `Usage:` line",
    "example": 'add epilog="Example:  co … <placeholder>"',
    "self_example": "no Example runs this command itself",
    "flags": "an Example uses a flag the page does not document",
    "refs": "an Example, Next or Back line names a command no page lists",
    "side_effect": "say what it changes with one of: " + LABELS.pattern.strip("\\b()").replace("|", ", "),
    "back": "no `Back:` line naming the parent page",
    "private": "an Example contains a real home path or a full 0x address; use a placeholder",
    "unreachable": "`co commands` lists it, but no page reachable from `co --help` does",
    "review": "a model reviewer flagged this page",
}


@dataclass(frozen=True)
class Finding:
    path: str
    check: str
    detail: str = ""

    @property
    def fix(self) -> str:
        return FIXES[self.check] + (f": {self.detail}" if self.detail else "")


def co_program() -> list:
    """The `co` beside this Python, so the audit runs the installation it belongs to."""
    beside = Path(sys.executable).with_name("co")
    return [str(beside)] if beside.exists() else [shutil.which("co") or "co"]


def run(words: list) -> tuple:
    """Run `co <words>` as an agent would, in an empty HOME and cwd.

    Returns (exit code, output without colour, whether it wrote a file).
    """
    home, work = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home),
           "NO_COLOR": "1", "COLUMNS": "200", "TERM": "dumb"}
    env.pop("FORCE_COLOR", None)
    env.pop("GITHUB_ACTIONS", None)
    done = subprocess.run([*co_program(), *words], cwd=work, env=env,
                          capture_output=True, text=True, timeout=120)
    wrote = any(home.iterdir()) or any(work.iterdir())
    return done.returncode, done.stdout, wrote


def help_page(words: list) -> tuple:
    return run([*words, "--help"])


# A Rich panel's title: `╭─ Send ──…`. Commands can sit under any title
# (co outlook groups them as "Send", "Scheduled sends", …); only Options and
# Arguments panels hold rows that are not commands.
PANEL = re.compile(r"╭─ ([^─]+?) ─")


def listed_commands(text: str) -> list:
    """The command names a page lists, skipping rows in Options and Arguments panels."""
    names = []
    for row in LISTED.finditer(text):
        titles = PANEL.findall(text[:row.start()])
        if not titles or titles[-1].strip() not in ("Options", "Arguments"):
            names.append(row.group(1))
    return names


def pages(start: str = "co", runner=help_page) -> dict:
    """Every page reachable by following printed names from `start`, walked level by level.

    {path: (exit code, text, wrote)}. A listed name whose page fails to print
    is still recorded, as a failure for check() to report.
    """
    found, level = {}, [start]
    with ThreadPoolExecutor(max_workers=16) as pool:
        while level:
            found.update(zip(level, pool.map(lambda path: runner(path.split()[1:]), level)))
            following = []
            for path in level:
                code, text, _ = found[path]
                if code != 0 or path == OWN_CONTRACT:
                    continue
                for name in listed_commands(text):
                    child = f"{path} {name}"
                    if child not in found and child not in following:
                        following.append(child)
            level = following
    return found


def registered(runner=run) -> set:
    """Every command path the CLI says it has, from `co commands`."""
    code, text, _ = runner(["commands"])
    return set(REGISTERED.findall(text)) if code == 0 else set()


def unreachable(found: dict, runner=run) -> list:
    """Commands `co commands` names that no reachable page lists."""
    return [Finding(path, "unreachable") for path in sorted(registered(runner) - set(found))
            if not path.startswith(OWN_CONTRACT + " ")]


def _examples(text: str):
    """Each `co …` invocation an Example line shows, as a word list."""
    for line in text.splitlines():
        if re.search(r"\bExamples?:", line):
            for part in re.split(r"\s\|\s", line.split(":", 1)[1]):
                part = part.strip().strip("│").strip()
                if part.startswith("co ") and part.count('"') % 2 == 0:
                    yield shlex.split(part.replace("\\", ""))


def _runs(words: list, found: dict) -> str:
    """The command an example runs: the longest printed path its words spell, skipping options."""
    path = "co"
    for word in words[1:]:
        if f"{path} {word}" in found:
            path = f"{path} {word}"
    return path


def check(path: str, page: tuple, found: dict) -> list:
    """Every hard rule for one page, decided from its printed text."""
    code, text, wrote = page
    out = []

    def add(rule, detail=""):
        out.append(Finding(path, rule, detail))

    if code != 0:
        add("exit0", f"exit {code}")
        return out
    if wrote:
        add("writes")
    # A hand-written page (`co proxy`) opens with its own name instead of Usage:.
    if "Usage:" not in text and not re.search(rf"^{re.escape(path)}\b", text, re.M):
        add("usage")
    examples = list(_examples(text))
    ran = {_runs(words, found) for words in examples}
    if not examples:
        add("example")
    elif not any(r == path or r.startswith(path + " ") for r in ran):
        add("self_example", f"examples run {', '.join(sorted(ran))}")
    for words in examples:
        # A flag is checked on the page of the command the example runs,
        # which for a group's example is a subcommand's page.
        target = found.get(_runs(words, found), page)[1]
        documented = "\n".join(line for line in target.splitlines() if not re.search(r"\bExamples?:", line))
        bad = [w.split("=")[0] for w in words if w.startswith("--") and w.split("=")[0] not in documented]
        if bad:
            add("flags", f"{' '.join(bad)} in `{' '.join(words)}`")
    for line in text.splitlines():
        if re.search(r"\b(Examples?|Next|Back):", line):
            for phrase in ("co" + tail for tail in PHRASE.findall(line)):
                if _runs(phrase.split(), found) == "co":
                    add("refs", phrase)
    if not LABELS.search(text):
        add("side_effect")
    if path != "co" and not re.search(r"\b(Back|Next):", text):
        add("back")
    for line in text.splitlines():
        if re.search(r"\bExamples?:", line) and PRIVATE.search(line):
            add("private", PRIVATE.search(line).group())
    return out


def audit(prefix: str = "co", runner=help_page, register=run) -> tuple:
    """(findings, pages checked) for every command at or under `prefix`, hard rules only."""
    found = pages("co", runner)
    within = {path: page for path, page in found.items()
              if (path == prefix or path.startswith(prefix + " ")) and not path.startswith(OWN_CONTRACT)}
    findings = [f for path, page in within.items() for f in check(path, page, found)]
    if prefix == "co":
        findings += unreachable(found, register)
    return findings, within


def inventory(found: dict) -> dict:
    """Each page's text, fingerprinted, so a later run can audit only what changed."""
    return {path: hashlib.sha256(text.encode()).hexdigest()[:16]
            for path, (_, text, _) in found.items() if not path.startswith(OWN_CONTRACT)}


PROMPT = """You operate a CLI named `co` and can only read its help pages. Goal: {goal}
Pages you have read so far:
{pages}
Reply with exactly one line:
HELP <command path>   to read that command's --help (e.g. HELP co gmail), or
RUN <full command>    when you know the command that achieves the goal."""


def walk(goal: str, model: str, max_pages: int = 8) -> tuple:
    """A text-only model reads help pages from `co --help` until it names one command.

    Returns (the command it named or None, the pages it read). Pages are never
    truncated: a first version cut them at 6,000 characters and hid half of
    `co --help`, and four "failures" were the harness's own.
    """
    from connectonion import llm_do

    read = {"co": help_page([])[1]}
    for _ in range(max_pages):
        shown = "\n\n".join(f"$ {path} --help\n{text}" for path, text in read.items())
        reply = str(llm_do(PROMPT.format(goal=goal, pages=shown), model=model)).strip()
        reply = reply.splitlines()[0].strip("` ") if reply else ""
        if reply.startswith("HELP "):
            path = reply[5:].strip()
            path = path if path.startswith("co") else f"co {path}"
            code, text, _ = help_page(path.split()[1:])
            read[path] = text if code == 0 else f"(no such command: {path})"
            continue
        return (reply.removeprefix("RUN ").strip() or None), list(read)
    return None, list(read)


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


def review(path: str, text: str, model: str):
    """A Finding when a model judges the page unclear, inaccurate, unrealistic or not simple.

    Run it after the hard rules: they are cheaper and certain, and a page that
    fails one is not worth a model's opinion yet.
    """
    from connectonion import llm_do

    verdict = llm_do(REVIEW_PROMPT.format(path=path, page=text), output=Review, model=model)
    failed = [name for name in ("clear", "effects_match", "example_realistic", "simple")
              if not getattr(verdict, name)]
    if not failed:
        return None
    return Finding(path, "review", f"{', '.join(failed)}; {verdict.suggestion}")
