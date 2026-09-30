"""
Purpose: Judge whether a command-line tool is fit for an agent harness, by running it and reading only what it prints (#1643, #1735)
LLM-Note:
  Dependencies: imports from [subprocess, concurrent.futures, pydantic, llm_do] | imported by [cli/commands/audit_commands.py, tests/unit/test_cli_help_contract.py, tests/unit/test_co_audit_rules.py, tests/e2e/real_api/test_cli_discovery_journeys.py]
  Data flow: help_page(argv) runs `<argv> --help` (or -h) → pages() walks every subcommand a page lists → check() rules on each printed page → score() per rule | review() → a model judges one page
  State/Effects: runs the program in a fresh empty HOME and cwd per page, stdin closed; review() calls a model
  Integration: one engine for `co audit <program>` and for CI | knows nothing of any source: an agent only ever sees output, and neither does this
  Errors: a finding names the rule and the fix; a page that hangs or fails to print is itself a finding

The question is the one an agent harness asks of any CLI, `co` or any other:
can an agent that has only this program's help find the command for a task,
run it safely, and know what it will change? One set of rules for every
program, hard rules first and judgement last:

- rules, decided from printed text: help prints and exits, does not hang
  waiting for input, writes nothing, has a usage line and an example of this
  command, every flag an example uses is documented, examples hold no private
  data, and every listed subcommand has its own page.
- review(): for pages that pass, a model judges what a rule cannot: clear,
  says what it reads or changes, a realistic example, simple, and whether a
  listed item has a short reference when the command acts on one.

`co`'s own house style (its fixed "what it changes" words, a Back line, and
every command in `co commands` reachable) is asserted by its CI test over the
same pages, not built into the tool.
"""

import hashlib
import os
import re
import shlex
import shutil
import site
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

# A row naming a subcommand: `│ name   summary` (Rich), `  name   summary`
# (click, uv, kubectl) or `  name:   summary` (gh).
ROW = re.compile(r"^(?:│ |\s{2,})([a-z][a-z0-9_-]*):?\s{2,}\S", re.M)
# A Rich panel's title: `╭─ Send ──…`. `co outlook` files commands under
# "Send" and "Scheduled sends"; only Options and Arguments hold other rows.
PANEL = re.compile(r"╭─ ([^─]+?) ─")
# A plain-text section heading: `Commands:`, `CORE COMMANDS`, `Read`. A line
# with an aligned column after it (`Keys:     model   …`) is a table row, not
# a heading, so its rows are not commands.
HEADER = re.compile(r"^(\S(?:(?!\s{2})[^\n])*?):?\s*$", re.M)
# Sections whose rows are not commands. Anything else may list commands under
# its own heading: `co rem` uses "Read" and "Keep it current", gh uses
# "CORE COMMANDS", co outlook's panels are "Send" and "Scheduled sends".
NOT_COMMANDS = re.compile(r"option|argument|flag|example|environment|usage|learn more|exit code|json field|help topic", re.I)
# argparse lists subcommands as `{init,run,list}`.
BRACES = re.compile(r"\{([a-z][a-z0-9_-]*(?:,[a-z][a-z0-9_-]*)+)\}")
USAGE = re.compile(r"^\s*usage\b", re.I | re.M)
# A real home directory or a full address in an example is someone's data, not
# a placeholder: 0x plus 64 hex is a ConnectOnion address, 40 hex an Ethereum
# one. Narrow on purpose: NAS paths, chat ids and `0x3f5a...c9e1` are fine.
PRIVATE = re.compile(r"/Users/[a-z][\w.-]*/|/home/[a-z][\w.-]*/[\w.-]+/|\b0x(?:[0-9a-fA-F]{64}|[0-9a-fA-F]{40})\b")
MAX_PAGES = 600
FIXES = {
    "prints": "`--help` (or -h) must print help and exit 0",
    "hangs": "`--help` did not return within 20 s; an agent cannot answer a prompt",
    "writes": "reading help wrote a file; help must not create state",
    "usage": "no usage line",
    "example": "no example; add one that runs this command with realistic placeholders",
    "self_example": "no example runs this command itself",
    "flags": "an example uses a flag this page does not document",
    "private": "an example contains a real home path or a full 0x address; use a placeholder",
    "params": "an option or argument has no description",
    "review": "a model reviewer flagged this page",
}
RULES = ("prints", "hangs", "writes", "usage", "example", "self_example", "flags", "private", "params")


@dataclass(frozen=True)
class Finding:
    path: str
    check: str
    detail: str = ""

    @property
    def fix(self) -> str:
        return FIXES[self.check] + (f": {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class Page:
    code: int
    text: str
    wrote: str = ""      # the first file reading help created, if any
    hung: bool = False


def program(name: str) -> list:
    """The executable to run for a program name: our own `co` beside this Python, else PATH."""
    if os.sep in name:
        return [name]
    beside = Path(sys.executable).with_name(name)
    if name == "co" and beside.exists():
        return [str(beside)]
    return [shutil.which(name) or name]


def run(argv: list) -> Page:
    """Run a command as an agent would: empty HOME and cwd, no terminal, no input."""
    home, work = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "NO_COLOR": "1",
           "COLUMNS": "200", "TERM": "dumb", "PAGER": "cat", "GIT_PAGER": "cat", "MANPAGER": "cat"}
    # Python's user site is derived from HOME. Keep installed CLI code
    # importable while isolating the command's data/configuration in a fresh
    # HOME; otherwise a pip --user `co` script crashes before printing help.
    env.setdefault("PYTHONUSERBASE", site.getuserbase())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("FORCE_COLOR", None)
    env.pop("GITHUB_ACTIONS", None)
    try:
        done = subprocess.run([*program(argv[0]), *argv[1:]], cwd=work, env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired:
        return Page(code=-1, text="", hung=True)
    created = [f for root in (home, work) for f in root.rglob("*") if f.is_file()]
    wrote = str(created[0].relative_to(home if created[0].is_relative_to(home) else work)) if created else ""
    return Page(done.returncode, done.stdout or done.stderr, wrote)


def help_page(argv: list) -> Page:
    """`<argv> --help`, or `-h` for tools that only know the short form."""
    page = run([*argv, "--help"])
    if page.hung or (page.code == 0 and page.text.strip()):
        return page
    short = run([*argv, "-h"])
    return short if short.code == 0 and short.text.strip() else page


# A token that names a parameter rather than describing it: `*`, `--overwrite`,
# `-n`, `local`, `TEXT`, `<PATH>`, `[required]`.
# `INTEGER RANGE [1<=x<=3650]`, `[name|modified|size]` and `[default: 30]` are
# types and defaults, not descriptions.
_NAME_ONLY = re.compile(r"^(\*|-{1,2}[\w-]+(?:[, ]+-{1,2}[\w-]+)*(?:[ =][A-Z_<\[][\w<>\[\].|-]*)?|[a-z_][\w-]*|"
                        r"[A-Z_]+(?: [A-Z_]+)*(?: \[[^\]]*\])?|<[^>]+>|\[[^\]]*\](?: \[[^\]]*\])*)$")


def undocumented(text: str) -> list:
    """Options and arguments a page lists with a name but no description.

    Read from Rich's Options/Arguments panels and from plain sections headed
    Options, Arguments or Flags. A row that starts with `[` continues the
    description above it and is not a parameter.
    """
    rows = []
    for panel in re.findall(r"╭─ (?:Options|Arguments) ─+╮\n(.*?)╰", text, re.S):
        rows += [line.strip().strip("│").strip() for line in panel.splitlines()]
    heading = ""
    for line in text.splitlines():
        if line[:1].strip():
            heading = line.strip()
        elif (re.search(r"option|argument|flag", heading, re.I) and not heading.startswith("╭")
              and line.strip().startswith("-")):
            # Plain text wraps descriptions onto indented lines of their own
            # (yt-dlp: "  ago"); only a line that starts with a flag is one.
            rows.append(line.strip())
    missing = []
    for row in rows:
        parts = [p for p in re.split(r"\s{2,}", row) if p]
        if parts and not row.startswith("[") and "--help" not in row and all(_NAME_ONLY.match(p) for p in parts):
            missing.append(parts[1] if parts[0] == "*" and len(parts) > 1 else parts[0])
    return missing


def listed_commands(text: str) -> list:
    """Subcommand names a help page lists, in any of the common layouts."""
    names = []
    for row in ROW.finditer(text):
        before = text[:row.start()]
        panels = PANEL.findall(before)
        # A plain-text row belongs to the nearest line above it that starts at
        # column 0; that line has to be a heading, not wrapped prose or a
        # `Keys:     model …` table row.
        above = [line for line in before.splitlines() if line[:1].strip()]
        heading = above[-1].strip() if above else ""
        plain = heading if HEADER.fullmatch(heading) and len(heading) <= 40 and not heading.endswith(".") else ""
        title = panels[-1] if panels else plain
        ok = bool(title) and not NOT_COMMANDS.search(title)
        if ok and row.group(1) not in names:
            names.append(row.group(1))
    for group in BRACES.findall(text):
        names += [name for name in group.split(",") if name not in names]
    return names


def pages(root: list, runner=help_page) -> dict:
    """Every page reachable from `<root> --help` by following listed subcommands, level by level."""
    found, level = {}, [" ".join(root)]
    # One `--help` per core: each is a process start, and more would slow the machine, not the walk.
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        while level and len(found) < MAX_PAGES:
            found.update(zip(level, pool.map(lambda path: runner(path.split()), level)))
            following = []
            for path in level:
                page = found[path]
                if page.code != 0:
                    continue
                for name in listed_commands(page.text):
                    child = f"{path} {name}"
                    if child not in found and child not in following:
                        following.append(child)
            level = following
    # A "subcommand" whose page is its parent's page word for word was a word
    # in the parent's text (gh codespace cp lists "mod" and "sum" as examples
    # of its arguments), not a command.
    return {path: page for path, page in found.items()
            if " " not in path or page.text != found.get(path.rsplit(" ", 1)[0], Page(0, "")).text}


def examples(text: str, name: str):
    """Each invocation of `name` an example shows: inline `Example:` lines, or an EXAMPLES section."""
    in_section = False
    for line in text.splitlines():
        stripped = line.strip().strip("│").strip()
        if re.fullmatch(r"examples?:?", stripped, re.I):
            in_section = True
            continue
        if in_section and line and not line[0].isspace():
            in_section = False
        inline = re.search(r"\bExamples?:\s*(.*)", line)
        candidates = re.split(r"\s\|\s", inline.group(1)) if inline else [stripped] if in_section else []
        for part in candidates:
            part = part.split(" #")[0]   # a shell comment, e.g. `gh epicsBy vilmibm #=> gh issue list …`
            part = part.strip().strip("│").strip().removeprefix("$ ")
            if part.startswith(name + " ") and part.count('"') % 2 == 0 and part.count("'") % 2 == 0:
                yield shlex.split(part.replace("\\", ""))


def _runs(words: list, found: dict, here: str) -> str:
    """The page an example runs: the longest listed path its words spell.

    An example may spell the command by an alias no page lists (`gh cs view`
    for `gh codespace view`). If it resolves only to an ancestor of this page
    but spells as many words, it is this command under another name.
    """
    path, stop = words[0], len(words)
    for i, (before, word) in enumerate(zip(words, words[1:]), start=1):
        if f"{path} {word}" in found:
            path = f"{path} {word}"
        elif not word.startswith("-") and not before.startswith("-"):
            stop = i   # neither a listed command nor an option's value: an alias, or an argument
            break
    # `gh cs view` on `gh codespace view`'s page: one unknown word in place of
    # the next command word, followed by the rest of this command's path.
    rest = here.split()[len(path.split()):] if here.startswith(path + " ") else []
    if len(rest) >= 2 and words[stop + 1:stop + len(rest)] == rest[1:]:
        return here
    return path


def check(path: str, page: Page, found: dict) -> list:
    """Every rule for one printed page: universal ones, plus ours when the program is `co`."""
    out = []

    def add(rule, detail=""):
        out.append(Finding(path, rule, detail))

    if page.hung:
        return [Finding(path, "hangs")]
    if page.code != 0 or not page.text.strip():
        return [Finding(path, "prints", f"exit {page.code}")]
    text, name = page.text, path.split()[0]
    if page.wrote:
        add("writes", page.wrote)
    # A hand-written page (`co proxy`) opens with its own name instead of a usage line.
    if not USAGE.search(text) and not re.search(rf"^{re.escape(path)}\b", text, re.M):
        add("usage")
    shown = list(examples(text, name))
    ran = {_runs(words, found, path) for words in shown}
    # An alias's page is its command's page: `gh co` shows `gh pr checkout` examples.
    same_page = {r for r in ran if r in found and found[r].text == text}
    if not shown:
        add("example")
    elif not any(r == path or r.startswith(path + " ") for r in ran) and not same_page:
        add("self_example", f"examples run {', '.join(sorted(ran))}")
    for words in shown:
        target = found.get(_runs(words, found, path), page).text
        documented = "\n".join(line for line in target.splitlines() if not re.search(r"\bExamples?:", line))
        bad = [w.split("=")[0] for w in words if w.startswith("--") and w.split("=")[0] not in documented]
        if bad:
            add("flags", f"{' '.join(bad)} in `{' '.join(words)}`")
    for line in text.splitlines():
        if re.search(r"\bExamples?:", line) and PRIVATE.search(line):
            add("private", PRIVATE.search(line).group())
    missing = undocumented(text)
    if missing:
        add("params", ", ".join(missing))
    return out


def audit(target: list, runner=help_page) -> tuple:
    """(findings, pages checked) for a program, or one of its commands.

    The walk always starts at the program's top page, as an agent does, then
    checks the pages at or under `target`.
    """
    target = list(target)
    found = pages(target[:1], runner)
    prefix = " ".join(target)
    within = {path: page for path, page in found.items() if path == prefix or path.startswith(prefix + " ")}
    return [f for path, page in within.items() for f in check(path, page, found)], within


def score(findings: list, checked: dict, rules=RULES) -> list:
    """(rule, pages passing, pages checked) per rule: the benchmark table."""
    failing = {rule: {f.path for f in findings if f.check == rule} for rule in rules}
    return [(rule, len(checked) - len(failing[rule]), len(checked)) for rule in rules]


def inventory(found: dict) -> dict:
    """Each page's text, fingerprinted, so a later run can audit only what changed."""
    return {path: hashlib.sha256(page.text.encode()).hexdigest()[:16] for path, page in found.items()}


PROMPT = """You operate a CLI named `{name}` and can only read its help pages. Goal: {goal}
Pages you have read so far:
{pages}
Reply with exactly one line:
HELP <command path>   to read that command's --help (e.g. HELP {name} <subcommand>), or
RUN <full command>    when you know the command that achieves the goal."""


def walk(goal: str, model: str, name: str = "co", max_pages: int = 8) -> tuple:
    """A text-only model reads help pages from `<name> --help` until it names one command.

    Returns (the command it named or None, the pages it read). Pages are never
    truncated: a first version cut them at 6,000 characters and hid half of
    `co --help`, and four "failures" were the harness's own.
    """
    from connectonion import llm_do

    read = {name: help_page([name]).text}
    for _ in range(max_pages):
        shown = "\n\n".join(f"$ {path} --help\n{text}" for path, text in read.items())
        reply = str(llm_do(PROMPT.format(name=name, goal=goal, pages=shown), model=model)).strip()
        reply = reply.splitlines()[0].strip("` ") if reply else ""
        if reply.startswith("HELP "):
            path = reply[5:].strip()
            path = path if path.startswith(name) else f"{name} {path}"
            page = help_page(path.split())
            read[path] = page.text if page.code == 0 else f"(no such command: {path})"
            continue
        return (reply.removeprefix("RUN ").strip() or None), list(read)
    return None, list(read)


class Review(BaseModel):
    """What a reviewer says about one help page."""
    clear: bool = Field(description="a newcomer knows when to use this command, from the first line")
    effects_match: bool = Field(description="the page says what the command reads, writes, sends or deletes, and it fits the command")
    example_realistic: bool = Field(description="the example is one a user would actually run")
    simple: bool = Field(description="short, plain words, no internal jargon needed to understand it")
    short_reference: bool = Field(
        description="if this command acts on an item from a list, its help offers a short row number or concise reference instead of requiring a long opaque ID or full name; true when this does not apply"
    )
    suggestion: str = Field(description="one concrete rewrite of the weakest sentence, or empty if all pass")


REVIEW_PROMPT = """You review one help page of a command-line tool that an AI agent may run
inside an agent harness. Its readers are people and agents deciding whether
and how to run the command. Judge only this page. If it acts on a listed item,
check whether the user can refer to that item briefly after listing it. Do not
penalize commands that do not select listed items.

$ {path} --help
{page}"""


def review(path: str, text: str, model: str):
    """A Finding when a model judges the page unclear, silent about effects, unrealistic or not simple.

    Run it after the rules: they are cheaper and certain, and a page that
    fails one is not worth a model's opinion yet.
    """
    from connectonion import llm_do

    verdict = llm_do(REVIEW_PROMPT.format(path=path, page=text), output=Review, model=model)
    failed = [name for name in ("clear", "effects_match", "example_realistic", "simple", "short_reference")
              if not getattr(verdict, name)]
    if not failed:
        return None
    return Finding(path, "review", f"{', '.join(failed)}; {verdict.suggestion}")


# ---------------------------------------------------------------------------
# The visual standard (#1997): does the output look finished in a terminal and
# stay plain everywhere else? Judged, like the rules above, only from what the
# program prints, run twice in a fresh empty HOME and cwd: once under a
# pseudo-terminal where colour is allowed, once into a pipe with NO_COLOR.

STYLE_RULES = ("hangs", "styled", "command_colour", "plain", "same_words", "field_dump")
FIXES.update({
    "styled": "prints no colour or weight in a terminal; style the heading, status marks and commands",
    "command_colour": "the command on a Next:, Example: or Back: line is not styled in a terminal",
    "plain": "prints escape codes under NO_COLOR into a pipe; colour only a terminal",
    "same_words": "the words differ between a terminal and a pipe; style the same words, do not change them",
    "field_dump": "prints raw internal fields; say it in words, one line per item, details behind --verbose",
})
# Leaf commands the style audit also runs, not just reads the help of. Two
# locks, both black-box: the last word is one of these verbs, and the
# command's own help page says Read-only. Nothing else is ever run, so the
# audit cannot send, delete or charge; a status-style command that wants to be
# checked says Read-only on its page.
SAFE_TO_RUN = ("status", "check", "ls", "doctor")
RUN_MARK = " [run]"
ESCAPE = re.compile(r"\x1b(?:\[[0-9;?]*[A-Za-z]|\][^\x07\x1b]*(?:\x07|\x1b\\))")
SGR = re.compile(r"\x1b\[([0-9;]*)m")
# `Next: co …`, `Example:  co …`, `Back: co --help`: the command a reader copies.
LABELLED = re.compile(r"\b(?:Next|Examples?|Back|Try|Run):\s+")
# `user_id: 42`, `lastSeen = 3`: an identifier with an underscore or an inner
# capital before a colon or an equals sign is a field name, not words. More
# than MAX_FIELDS of them in one output is an internal record printed as it is.
# A Python or JSON literal on its own line (`{'id': 1}`) counts as one each.
FIELD = re.compile(r"^\s*(?:[-*•]\s+)?([a-z][a-z0-9]*(?:_[a-z0-9]+)+|[a-z]+(?:[A-Z][a-z0-9]*)+)\s*[:=]\s*\S", re.M)
REPR = re.compile(r"^\s*[\[{]\s*['\"]\w+['\"]\s*:", re.M)
MAX_FIELDS = 2
# Seconds a run may take, like --help. Nothing it runs may wait for input.
RUN_TIMEOUT = 20


@dataclass(frozen=True)
class Output:
    code: int
    out: str
    err: str
    hung: bool = False


def _style_env(home: Path, terminal: bool) -> dict:
    """Both runs share width and HOME rules; only the colour signals differ."""
    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home), "COLUMNS": "200", "LINES": "50",
           "PAGER": "cat", "GIT_PAGER": "cat", "MANPAGER": "cat", "PYTHONDONTWRITEBYTECODE": "1"}
    env.setdefault("PYTHONUSERBASE", site.getuserbase())
    for name in ("FORCE_COLOR", "NO_COLOR", "GITHUB_ACTIONS", "CLICOLOR_FORCE", "PY_COLORS", "TERMINAL_WIDTH"):
        env.pop(name, None)
    env.update({"TERM": "xterm-256color"} if terminal else {"NO_COLOR": "1", "TERM": "dumb"})
    return env


def _scrub(text: str, home: Path, work: Path) -> str:
    """Each run gets its own temporary HOME and cwd; name them the same way in
    both, or a printed path makes the words differ when nothing else did."""
    for real, name in ((home, "~"), (work, ".")):
        for spelling in {str(real), str(real.resolve())}:
            text = text.replace(spelling, name)
    return text


def run_plain(argv: list) -> Output:
    """The run a pipe, a log file or launchd sees: NO_COLOR, no terminal, no input."""
    home, work = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    try:
        done = subprocess.run([*program(argv[0]), *argv[1:]], cwd=work, env=_style_env(home, False),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        return Output(-1, "", "", hung=True)
    return Output(done.returncode, _scrub(done.stdout, home, work), _scrub(done.stderr, home, work))


def _drain(fd: int, into: list) -> None:
    """Read a pty until its far end closes, which a pty reports as EIO."""
    while True:
        try:
            data = os.read(fd, 65536)
        except OSError:
            return
        if not data:
            return
        into.append(data)


def run_terminal(argv: list) -> Output:
    """The run a person at a terminal sees: stdout and stderr each a 200-column pty.

    Without pty (Windows) it falls back to FORCE_COLOR into a pipe, which Rich
    and Typer honour; a program that only checks isatty() then looks plain.
    """
    home, work = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    env, command = _style_env(home, True), [*program(argv[0]), *argv[1:]]
    try:
        import fcntl
        import pty
        import struct
        import termios
    except ImportError:
        try:
            done = subprocess.run(command, cwd=work, env={**env, "FORCE_COLOR": "1"}, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            return Output(-1, "", "", hung=True)
        return Output(done.returncode, _scrub(done.stdout, home, work), _scrub(done.stderr, home, work))
    import signal
    import threading

    pairs = [pty.openpty() for _ in range(2)]
    for _, follower in pairs:
        fcntl.ioctl(follower, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 200, 0, 0))
    chunks = [[], []]
    proc = subprocess.Popen(command, cwd=work, env=env, stdin=subprocess.DEVNULL,
                            stdout=pairs[0][1], stderr=pairs[1][1], start_new_session=True)
    for _, follower in pairs:
        os.close(follower)
    readers = [threading.Thread(target=_drain, args=(leader, into), daemon=True)
               for (leader, _), into in zip(pairs, chunks)]
    for reader in readers:
        reader.start()
    try:
        code, hung = proc.wait(timeout=RUN_TIMEOUT), False
    except subprocess.TimeoutExpired:
        # Its own session, so the whole group goes: a child it started would
        # otherwise keep the pty open and the run would never finish.
        os.killpg(proc.pid, signal.SIGKILL)
        code, hung = proc.wait(), True
    # A child it left running may hold the pty open; stop waiting after a moment.
    for reader in readers:
        reader.join(timeout=5)
    for leader, _ in pairs:
        os.close(leader)
    for reader in readers:
        reader.join(timeout=5)
    out, err = (_scrub(b"".join(c).decode("utf-8", "replace").replace("\r\n", "\n"), home, work) for c in chunks)
    return Output(code, out, err, hung)


def screen(raw: str) -> str:
    """What stays on screen: a spinner redrawn with \\r, or a live display
    erased with cursor-up and erase-line, leaves only what was last drawn."""
    lines, here = [], ""
    for piece in re.split(r"(\r|\n|\x1b\[\d*A|\x1b\[[0-2]?K)", raw):
        if piece == "\n":
            lines.append(here)
            here = ""
        elif piece == "\r" or re.fullmatch(r"\x1b\[[0-2]?K", piece):
            here = ""
        elif re.fullmatch(r"\x1b\[\d*A", piece):
            up = min(int(piece[2:-1] or 1), len(lines))
            here = lines[-up] if up else ""
            del lines[len(lines) - up:]
        else:
            here += piece
    return "\n".join(lines + [here])


def _styled_at(line: str, index: int) -> bool:
    """Whether the visible character at `index` of a raw line is inside a style."""
    on, seen = False, 0
    for part in re.split(r"(\x1b\[[0-9;?]*[A-Za-z])", line):
        match = SGR.fullmatch(part)
        if match:
            on = any(code not in ("", "0") for code in match.group(1).split(";"))
        elif not part.startswith("\x1b"):
            if index < seen + len(part):
                return on
            seen += len(part)
    return False


def style_check(path: str, terminal: Output, plain: Output) -> list:
    """The visual standard for one output: the terminal run against the plain run.

    `path` ends in RUN_MARK for a command that was run rather than asked for
    help; only those are checked for field dumps, since a help page's option
    rows are meant to look like a list.
    """
    out, name = [], path.split()[0]

    def add(rule, detail=""):
        out.append(Finding(path, rule, detail))

    if terminal.hung or plain.hung:
        return [Finding(path, "hangs", "while running it")]
    tty = screen(terminal.out) + "\n" + screen(terminal.err)
    shown = ESCAPE.sub("", tty)
    if shown.strip() and not SGR.search(tty):
        add("styled")
    for raw in tty.splitlines():
        seen = ESCAPE.sub("", raw)
        starts = [m.end() for m in LABELLED.finditer(seen) if seen.startswith(name + " ", m.end())]
        if any(not _styled_at(raw, start) for start in starts):
            add("command_colour", seen.strip()[:80])
            break
    piped = plain.out + "\n" + plain.err
    escaped = [line for line in piped.splitlines() if "\x1b" in line]
    if escaped:
        add("plain", ESCAPE.sub("", escaped[0]).strip()[:80])
    words = [shown.split(), ESCAPE.sub("", piped).split()]
    if words[0] != words[1]:
        at = next((i for i, (a, b) in enumerate(zip(*words)) if a != b), min(map(len, words)))
        add("same_words", f"terminal {' '.join(words[0][at:at + 4])!r}, pipe {' '.join(words[1][at:at + 4])!r}")
    if path.endswith(RUN_MARK):
        fields = FIELD.findall(piped) + ["{…}"] * len(REPR.findall(piped))
        if len(fields) > MAX_FIELDS:
            add("field_dump", ", ".join(dict.fromkeys(fields))[:80])
    return out


def runnable(path: str, page: Page) -> bool:
    """A leaf whose verb is safe to run and whose own help says Read-only."""
    return (path.split()[-1] in SAFE_TO_RUN and page.code == 0 and "Read-only" in page.text
            and not listed_commands(page.text))


def style_audit(checked: dict, terminal=None, plain=None) -> tuple:
    """(findings, outputs checked) under the visual standard: every help page
    checked, plus one run of each read-only status-style command among them."""
    terminal, plain = terminal or run_terminal, plain or run_plain
    jobs = [(path, [*path.split(), "--help"]) for path, page in checked.items() if page.code == 0]
    jobs += [(path + RUN_MARK, path.split()) for path, page in checked.items() if runnable(path, page)]

    def one(job):
        path, argv = job
        return style_check(path, terminal(argv), plain(argv))

    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        results = list(pool.map(one, jobs))
    return [f for found in results for f in found], {path: checked[path.removesuffix(RUN_MARK)] for path, _ in jobs}


def by_group(findings: list, checked: dict) -> list:
    """(group, outputs passing every rule, outputs checked), worst first: the fan-out table."""
    groups = {}
    for path in checked:
        groups.setdefault(" ".join(path.removesuffix(RUN_MARK).split()[:2]), []).append(path)
    failing = {f.path for f in findings}
    rows = [(group, sum(p not in failing for p in paths), len(paths)) for group, paths in groups.items()]
    return sorted(rows, key=lambda row: (row[1] / row[2], row[0]))
