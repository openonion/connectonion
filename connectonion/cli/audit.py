"""
Purpose: Judge whether a command-line tool is fit for an agent harness, by running it and reading only what it prints (#1643, #1735)
LLM-Note:
  Dependencies: imports from [subprocess, concurrent.futures, pydantic, llm_do] | imported by [cli/commands/audit_commands.py, tests/unit/test_cli_help_contract.py, tests/unit/test_co_audit_rules.py, tests/e2e/real_api/test_cli_discovery_journeys.py]
  Data flow: help_page(argv) runs `<argv> --help` (or -h) → pages() walks every subcommand a page lists → check() rules on each printed page → look() compares it with the same page in a terminal → score() per rule | review() → a model judges one page
  State/Effects: runs the program in a fresh empty HOME and cwd per page (as an agent, then as a person's terminal), stdin closed; review() calls a model
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
- look: run again the way a person's terminal runs it (stdout and stderr each
  a pty), the page says the same words, nothing repeated at the top, no word
  coloured in pieces, no emoji panel title, a status command ends on Next,
  with colour only there (#1997, #2008).
- review(): for pages that pass, a model judges what a rule cannot: clear,
  says what it reads or changes, a realistic example, simple, and whether a
  listed item has a short reference when the command acts on one.

`co`'s own house style (its fixed "what it changes" words, a Back line, and
every command in `co commands` reachable) is asserted by its CI test over the
same pages, not built into the tool.
"""

import hashlib
import io
import os
import re
import shlex
import shutil
import site
import subprocess
import sys
import tempfile
from collections import Counter
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
    "look": "a terminal and a pipe must show the same words, in colour only in the terminal",
    "review": "a model reviewer flagged this page",
}
RULES = ("prints", "hangs", "writes", "usage", "example", "self_example", "flags", "private", "params", "look")


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
    err: str = ""        # stderr when `text` is stdout: where a command's Next line goes


def program(name: str) -> list:
    """The executable to run for a program name: our own `co` beside this Python, else PATH."""
    beside = Path(sys.executable).with_name(name)
    if name == "co" and beside.exists():
        return [str(beside)]
    return [shutil.which(name) or name]


# How an agent runs a command, and how a person's terminal does. Output is
# captured either way; FORCE_COLOR says what a terminal would have decided.
AGENT = {"NO_COLOR": "1", "COLUMNS": "200", "TERM": "dumb"}
PERSON = {"FORCE_COLOR": "1", "COLUMNS": "100", "TERM": "xterm-256color"}
# A key in the environment is the user's as much as one in HOME. With one set
# (CI sets OPENONION_API_KEY), `co doctor` in STATUS calls its backend, and a
# network answer can differ between the two runs look compares.
CREDENTIAL = re.compile(r"_(API_KEY|TOKEN|SECRET)$")


def run(argv: list, terminal: bool = False) -> Page:
    """Run a command as an agent would: empty HOME and cwd, no credentials, no terminal, no input.

    `terminal=True` runs it as a person's terminal would instead: colour on,
    100 columns, the same empty HOME and no input.
    """
    home, work = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    env = {**{k: v for k, v in os.environ.items() if not CREDENTIAL.search(k)},
           "HOME": str(home), "USERPROFILE": str(home), **(PERSON if terminal else AGENT),
           "PAGER": "cat", "GIT_PAGER": "cat", "MANPAGER": "cat"}
    # Python's user site is derived from HOME. Keep installed CLI code
    # importable while isolating the command's data/configuration in a fresh
    # HOME; otherwise a pip --user `co` script crashes before printing help.
    env.setdefault("PYTHONUSERBASE", site.getuserbase())
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("NO_COLOR" if terminal else "FORCE_COLOR", None)
    env.pop("TTY_COMPATIBLE", None)   # Rich obeys it before NO_COLOR and FORCE_COLOR
    env.pop("GITHUB_ACTIONS", None)
    try:
        done = (_in_terminal if terminal else _in_pipe)([*program(argv[0]), *argv[1:]], work, env)
    except subprocess.TimeoutExpired:
        return Page(code=-1, text="", hung=True)
    created = [f for root in (home, work) for f in root.rglob("*") if f.is_file()]
    wrote = str(created[0].relative_to(home if created[0].is_relative_to(home) else work)) if created else ""
    return Page(done.returncode, done.stdout or done.stderr, wrote, err=done.stderr if done.stdout else "")


RUN_TIMEOUT = 20   # seconds; nothing a page or a status command runs may wait for input


def _in_pipe(command: list, work: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=work, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=RUN_TIMEOUT)


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


def _in_terminal(command: list, work: Path, env: dict) -> subprocess.CompletedProcess:
    """stdout and stderr each a 100-column pty, as in a person's terminal (#2008).

    With stderr a pipe, whatever a program prints only when stderr is a
    terminal never reached the audit: `[env] …/keys.env` opened every co
    command 2-3 times in a real terminal while the look rule saw nothing.
    Without pty (Windows) it falls back to pipes; FORCE_COLOR still colours.
    """
    try:
        import fcntl
        import pty
        import termios
    except ImportError:
        return _in_pipe(command, work, env)
    import signal
    import struct
    import threading

    pairs = [pty.openpty() for _ in range(2)]
    for _, follower in pairs:
        fcntl.ioctl(follower, termios.TIOCSWINSZ, struct.pack("HHHH", 50, int(env.get("COLUMNS", 100)), 0, 0))
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
        code = proc.wait(timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)   # its own session: a child would keep the pty open
        proc.wait()
        raise
    finally:
        for reader in readers:
            reader.join(timeout=5)   # a child left running may hold the pty; stop waiting
        for leader, _ in pairs:
            os.close(leader)
    out, err = (b"".join(c).decode("utf-8", "replace").replace("\r\n", "\n") for c in chunks)
    return subprocess.CompletedProcess(command, code, out, err)


def help_page(argv: list, terminal: bool = False) -> Page:
    """`<argv> --help`, or `-h` for tools that only know the short form."""
    page = run([*argv, "--help"], terminal)
    if page.hung or (page.code == 0 and page.text.strip()):
        return page
    short = run([*argv, "-h"], terminal)
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


# Colour and cursor codes: CSI (`ESC[1;36m`) and OSC (terminal links).
ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
SGR = re.compile(r"\x1b\[[0-9;]*m")
# What a printout says is everything but whitespace and the box and block
# characters drawn to the terminal's width (a panel's frame, a rule, a bar):
# at 100 columns the same words wrap and frame differently than at 200.
FRAME = re.compile(r"[\s─-▟]+")
# Each run's own empty HOME and cwd, which a status command may print.
SCRATCH = re.compile(re.escape(tempfile.gettempdir()) + r"/tmp\w+")
# Read-only `co` commands a person runs to see where things stand: safe in an
# empty HOME, fast, and offline there. Their output is held to the look rule
# as every help page is. One line each.
STATUS = (
    "co status",
    "co doctor",
    "co commands",
    "co rem status",
    "co auth status",
    "co whatsapp check",   # every inbox `check` prints through the same handler
)
# Lines of a printout searched for a repeat: startup noise comes first (#2008).
TOP = 5
# Emoji a panel title must not carry: pictographs and the miscellaneous
# symbols (⚠ ☁), not the dingbats ✓ ✗ that mark a row.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u26FF]")
PANEL_TOP = re.compile(r"^\s*[╭┌┏]")


def _tokens(text: str) -> list:
    return [t for t in FRAME.split(SCRATCH.sub("~", ANSI.sub("", text))) if t]


def _difference(said: str, shown: str) -> str:
    """The words only one side has, or "" when both say the same thing laid out differently.

    Compared as the characters each prints, in any order. Order cannot be
    held: in a table narrowed to 100 columns a long value folds onto the next
    line (`read-only|…|danger` / `-full-access`) while the description beside
    it carries on, so the same words interleave differently. What a narrower
    terminal must not do is lose or change any: Rich's default for a long
    path in a table is to cut it to `connec…`.
    """
    a, b = _tokens(said), _tokens(shown)
    if Counter("".join(a)) == Counter("".join(b)):
        return ""
    extra, missing = Counter(b) - Counter(a), Counter(a) - Counter(b)
    return f"it shows {' '.join(list(extra)[:4]) or '(nothing)'} where an agent reads {' '.join(list(missing)[:4]) or '(nothing)'}"


def _repeated_at_top(text: str) -> str:
    """The first line printed twice among the first TOP lines, or "".

    `[env] …/keys.env` opened every co command two or three times in a real
    terminal (#2008); a blank line or a frame drawn twice is not a repeat.
    """
    seen = set()
    for line in [ANSI.sub("", line).strip() for line in text.splitlines() if line.strip()][:TOP]:
        if line in seen and FRAME.sub("", line):
            return line
        seen.add(line)
    return ""


def _pieces(shown: str) -> list:
    """Words a terminal printout colours in pieces: letters or digits in two styles inside one word.

    Rich's default highlighter does this to whatever looks like a number, date
    or path (`co 1.9.0a5` with `1.9` alone in cyan, #2008). A word in one style
    beside punctuation in another (`(co auth)`) is not pieces.
    """
    found = []
    for line in shown.splitlines():
        chars, state = [], ""
        for part in re.split(r"(\x1b\[[0-9;]*m)", re.sub(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)", "", line)):
            if SGR.fullmatch(part):
                state = "" if part in ("\x1b[0m", "\x1b[m") else state + part
            else:
                chars += [(c, state) for c in ANSI.sub("", part)]
        word = []
        for c, style in chars + [(" ", "")]:
            if not c.isspace():
                word.append((c, style))
                continue
            if len({style for c, style in word if c.isalnum()}) > 1:
                found.append("".join(c for c, _ in word))
            word = []
    return found


def _unshaped_next(shown: str) -> list:
    """`Next:` lines of a terminal printout not drawn the way style.next_line draws them."""
    from rich.console import Console

    from .style import THEME, next_line

    buffer = io.StringIO()
    Console(file=buffer, theme=THEME, force_terminal=True, color_system="256").print(next_line("co"))
    # `Next:` in its style, then the command in its own; a few words may come
    # between them (`Next: See every list:  co trust list`).
    label, rest = buffer.getvalue().split(" ", 1)
    opens = rest.split("co")[0]
    return [line.strip() for line in shown.splitlines() if ANSI.sub("", line).lstrip().startswith("Next:")
            and not (line.lstrip().startswith(label + " ") and opens in line)]


def look(path: str, plain: Page, styled: Page, output: bool = False) -> list:
    """The same page, or a status command's `output`, as an agent reads it and as a person's terminal shows it.

    Colour in a pipe and different words in a terminal are faults in any
    program. No colour in a terminal is a fault only in `co`: plenty of good
    CLIs print plain help on purpose, and nothing about that stops an agent,
    but `co` promises one look everywhere (#1997), so a plain co page is one
    nobody moved onto connectonion/cli/style.py. The Next-line shape is co's
    for the same reason.
    """
    what, ours = ("output" if output else "help"), path.split()[0] == "co"
    if styled.hung or styled.code != plain.code:
        return [Finding(path, "look", f"{what} in a terminal: exit {styled.code}{' (hung)' if styled.hung else ''}")]
    said, shown = plain.text + plain.err, styled.text + styled.err
    details = []
    if ANSI.search(said):
        details.append("has colour codes under NO_COLOR, TERM=dumb and a pipe")
    if ours and not SGR.search(shown):
        details.append("has no colour in a terminal; print it through connectonion/cli/style.py")
    moved = _difference(said, shown)
    if moved:
        details.append(f"shows different words in a terminal: {moved}")
    twice = _repeated_at_top(styled.err) or _repeated_at_top(styled.text) or _repeated_at_top(shown)
    if twice:
        details.append(f"prints `{twice}` twice at the top")
    if ours:
        pieces = _pieces(shown)
        if pieces:
            details.append(f"has words coloured in pieces (auto-highlighting; make the Console with "
                           f"highlight=False): {' '.join(dict.fromkeys(pieces[:4]))}")
        titles = [ANSI.sub("", line).strip() for line in shown.splitlines()
                  if PANEL_TOP.match(ANSI.sub("", line)) and EMOJI.search(line)]
        if titles:
            details.append(f"has an emoji in a panel title: {titles[0][:60]}")
    if output and ours:
        details += [f"prints a Next: line without style.next_line's shape: {ANSI.sub('', line)}"
                    for line in _unshaped_next(shown)]
        if not any(ANSI.sub("", line).lstrip().startswith("Next:") for line in shown.splitlines()):
            details.append("has no Next: line; a status command ends on the step to take (style.next_line)")
    return [Finding(path, "look", f"{what} {detail}") for detail in details]


def looks(within: dict, findings: list, runner=help_page, output=run) -> list:
    """The look rule on every page that printed, and on each STATUS command in reach, run the second way here."""
    printed = [path for path in within if not any(f.path == path and f.check in ("prints", "hangs") for f in findings)]
    status = [path for path in STATUS if path in within]
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        shown = list(pool.map(lambda path: runner(path.split(), terminal=True), printed))
        both = list(pool.map(lambda path: (output(path.split()), output(path.split(), terminal=True)), status))
    return ([f for path, page in zip(printed, shown) for f in look(path, within[path], page)]
            + [f for path, (plain, styled) in zip(status, both) for f in look(path, plain, styled, output=True)])


def audit(target: list, runner=help_page, output=run) -> tuple:
    """(findings, pages checked) for a program, or one of its commands.

    The walk always starts at the program's top page, as an agent does, then
    checks the pages at or under `target`, and runs just those a second time
    as a person's terminal would for the look rule.
    """
    target = list(target)
    found = pages(target[:1], runner)
    prefix = " ".join(target)
    within = {path: page for path, page in found.items() if path == prefix or path.startswith(prefix + " ")}
    findings = [f for path, page in within.items() for f in check(path, page, found)]
    return findings + looks(within, findings, runner, output), within


def score(findings: list, checked: dict) -> list:
    """(rule, pages passing, pages checked) per rule: the benchmark table."""
    failing = {rule: {f.path for f in findings if f.check == rule} for rule in RULES}
    return [(rule, len(checked) - len(failing[rule]), len(checked)) for rule in RULES]


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
