"""The unit run fails when a test process writes the real ~/.co, and only then.

Imported at the top of tests/conftest.py, before connectonion, so its audit
hook is installed before any module constant is built and before any test runs.

Why: `_never_touch_the_real_home` repoints HOME and Path.home() per test, which
reaches only code that asks at call time. A module constant such as
`SSH_PRIVATE_KEY = Path.home() / ".co" / "ssh" / "id_ed25519"` is built at
import and keeps the real home. On 2026-11-08 a green unit run wrote
id_ed25519_prod and id_ed25519_staging into the real ~/.co/ssh that way, on two
machines.

Two instruments, because each alone is wrong in one direction:

- An audit hook in every pytest process (controller and each xdist worker)
  records each write it makes under the real ~/.co -- write-mode open, rename,
  replace, remove, mkdir, chmod/utime, shutil copy/move/rmtree, sqlite3 -- with
  the running test's node id, to a per-run file. Any record fails the run,
  naming test and path, with no allowlist. It cannot see a subprocess.
- One `find -cnewer` pass over the real ~/.co by lstat only (never opening a
  file; ~/.co/ssh holds private keys), taken by the controller at the end:
  every entry whose ctime moved since the session started. It sees every
  writer, including the operator's own: scheduled REM rounds, token refresh in
  keys.env, mail stores, another worktree's test run. A change it sees with no
  matching record is printed as "changed by another process" and does not fail:
  a guard that goes red whenever the machine is busy is a guard people learn to
  ignore. A change under ssh/ is printed loudly, but is not a failure either --
  `co server new` and `co keys` legitimately write there, and a test's
  subprocess (invisible to the hook) is indistinguishable from them by stat.
  A removed entry shows as its directory, unless another change in that
  directory is already listed.

A pytest started from inside a running pytest (CONNECTONION_REAL_HOME_GUARD_OWNER
names a live owner) keeps the audit hook and writes to the owner's records,
so its writes still turn the owner red; it skips the pass over ~/.co and never
reads or removes the owner's records.

CONNECTONION_TEST_REAL_HOME points both at a scratch home for the guard's own
red-first check; nothing else should set it.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

_GUARD_SELF_TEST = bool(os.environ.get("CONNECTONION_TEST_REAL_HOME"))
# Captured at import, before anything is patched.
# Watch the account's own home, not $HOME: runs are told to use HOME=$(mktemp -d),
# and a guard watching that scratch home proves nothing about the real ~/.co.
def _account_home():
    """The account's own home; Windows has no pwd module, and its HOME override is rare."""
    if os.name == "nt":
        return os.path.expanduser("~")
    import pwd
    return pwd.getpwuid(os.getuid()).pw_dir


REAL_CO = Path(os.environ.get("CONNECTONION_TEST_REAL_HOME") or _account_home()) / ".co"
# Module constants froze whatever $HOME was at import; conftest rebases from here.
IMPORT_CO = Path(os.environ.get("CONNECTONION_TEST_REAL_HOME") or os.path.expanduser("~")) / ".co"
# The REM reader's saved pages (connectonion/rem/reader.py, _cache_dir) live
# outside ~/.co, in the real temporary directory: the owner's own reader cache.
# conftest points each test at its own; the same hook catches a test that writes
# the real one, and the run fails naming it.
REAL_REM_CACHE = None if os.name == "nt" else Path(tempfile.gettempdir()) / f"co-rem-cache-{os.getuid()}"
_PREFIXES = tuple({str(REAL_CO), os.path.realpath(REAL_CO),
                   *((str(REAL_REM_CACHE), os.path.realpath(REAL_REM_CACHE)) if REAL_REM_CACHE else ())})

# Left out of the pass over ~/.co because they are large and churn constantly (the
# `co browser` daemon's profile alone is thousands of files); the audit hook
# still covers them. A scratch home has no live writers, so nothing is left out.
_NOT_IN_MANIFEST = frozenset() if _GUARD_SELF_TEST else frozenset({
    "browser", "browser_profile", "browser_context", "browser_network", "browser.log", "logs",
})

# One file per run, shared by the controller and the workers it spawns (they
# inherit the environment). A worker finds it already set.
_RECORDS_ENV = "CONNECTONION_TEST_HOME_WRITES"
if not os.environ.get(_RECORDS_ENV):
    _fd, _path = tempfile.mkstemp(prefix="co-real-home-writes-", suffix=".tsv")
    os.close(_fd)
    os.environ[_RECORDS_ENV] = _path
_RECORDS = os.environ[_RECORDS_ENV]

# The pytest that owns the report marks itself for every process it starts. A
# pytest run from inside it (a test that runs `pytest --collect-only`) keeps its
# audit hook, whose records land in the owner's file and turn the owner red, but
# skips its own look at ~/.co and leaves the owner's records file alone.
_OWNER_ENV = "CONNECTONION_REAL_HOME_GUARD_OWNER"


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


_owner = os.environ.get(_OWNER_ENV, "")
_NESTED = _owner.isdigit() and int(_owner) != os.getpid() and _alive(int(_owner))
if not _NESTED:
    os.environ[_OWNER_ENV] = str(os.getpid())

# ---- the audit hook ----------------------------------------------------------

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
# event -> indexes of the args that name a path being written
_PATH_ARGS = {
    "os.rename": (0, 1), "os.replace": (0, 1), "os.remove": (0,), "os.rmdir": (0,),
    "os.mkdir": (0,), "os.truncate": (0,), "os.chmod": (0,), "os.utime": (0,),
    "os.symlink": (1,), "os.link": (1,), "shutil.copyfile": (1,), "shutil.copytree": (1,),
    "shutil.move": (0, 1), "shutil.rmtree": (0,), "sqlite3.connect": (0,),
}
_current_test = "<outside any test: import, collection or session hooks>"
_recording = False
# Bound now: a test that patches builtins.open or os.path must not reach the hook.
_open, _abspath, _fsdecode = open, os.path.abspath, os.fsdecode


def _under_real_co(path):
    if isinstance(path, int):
        return None  # a file descriptor
    try:
        text = _fsdecode(path)
    except TypeError:
        return None
    if ".co" not in text and "co-rem-cache-" not in text:  # the cheap test first; this runs on every open
        return None
    text = _abspath(text)
    return text if any(text == p or text.startswith(p + os.sep) for p in _PREFIXES) else None


def _is_write_open(args):
    _path, mode, flags = args
    if isinstance(flags, int) and flags & _WRITE_FLAGS:
        return True
    return isinstance(mode, str) and any(c in mode for c in "wax+")


def _audit(event, args):
    global _recording
    if event == "open":
        if not _is_write_open(args):
            return
        indexes = (0,)
    else:
        indexes = _PATH_ARGS.get(event)
        if indexes is None:
            return
    if _recording:
        return  # our own append below
    for i in indexes:
        hit = _under_real_co(args[i]) if i < len(args) else None
        if hit:
            _recording = True
            try:
                with _open(_RECORDS, "a", encoding="utf-8") as out:
                    out.write(f"{_current_test}\t{event}\t{hit}\n")
            finally:
                _recording = False


sys.addaudithook(_audit)


def pytest_runtest_logstart(nodeid, location):
    global _current_test
    _current_test = nodeid


def pytest_runtest_logfinish(nodeid, location):
    global _current_test
    _current_test = "<between tests>"


# ---- what changed during the run ---------------------------------------------

def changed_since(marker):
    """Relative paths under the real ~/.co whose ctime is newer than marker's mtime.

    One `find -cnewer` pass at the end of the run, by lstat only (never opening a
    file). ctime moves on every content write, chmod, rename and link, including
    an in-place append that leaves the directory's mtime alone; a created or
    removed entry also moves its directory's. So nothing is hidden, and no start
    snapshot is needed. Measured on a 1M-entry ~/.co: the Python lstat walk this
    replaces took ~80 s and ran twice, at start and end; this one pass ~35 s.
    """
    if not REAL_CO.is_dir():
        return []
    skip = [arg for name in sorted(_NOT_IN_MANIFEST) for arg in ("-o", "-path", str(REAL_CO / name))][1:]
    prune = ["(", *skip, ")", "-prune", "-o"] if skip else []
    out = subprocess.run(["find", "-H", str(REAL_CO), *prune, "-cnewer", marker, "-print"],
                         capture_output=True, text=True).stdout  # unreadable entries go to stderr
    return sorted(os.path.relpath(line, REAL_CO) for line in out.splitlines() if line)


def unexplained(changed, by_us):
    """Changes this pytest's records do not explain, labelled for the report.

    A directory is listed only when nothing listed under it explains it: then an
    entry in it was removed or renamed away.
    """
    explained = set(changed) | by_us
    found = []
    for path in changed:
        if path in by_us:
            continue
        if os.path.isdir(REAL_CO / path):
            inside = "" if path == "." else path + os.sep
            if any(p != path and p.startswith(inside) for p in explained):
                continue
            found.append(("entry removed in", path))
        else:
            found.append(("changed", path))
    return found


# ---- naming the other writer -------------------------------------------------

def _rem_turns(changed):
    """REM `.state/turns` entries changed during the run."""
    return [p for p in changed if p.startswith("rem") and f"{os.sep}.state{os.sep}turns{os.sep}" in os.sep + p]


def _live_co_processes():
    """`co`/`codex` processes running now that this pytest did not start."""
    try:
        out = subprocess.run(["ps", "-Ao", "pid=,ppid=,command="], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = [line.split(None, 2) for line in out.splitlines() if len(line.split(None, 2)) == 3]
    parent = {int(pid): int(ppid) for pid, ppid, _ in rows}
    mine = os.getpid()

    def descends_from_me(pid):
        while pid > 1:
            if pid == mine:
                return True
            pid = parent.get(pid, 1)
        return False

    found = []
    for pid, _ppid, command in rows:
        argv = command.split()
        names = {os.path.basename(a) for a in argv[:2]}
        if names & {"co", "codex"} and not descends_from_me(int(pid)) and "pytest" not in command:
            found.append(f"{pid} {command[:120]}")
    return found


# ---- session hooks (controller only; the workers share its filesystem) -------

def pytest_sessionstart(session):
    if hasattr(session.config, "workerinput") or _NESTED:
        return  # the owner reads the records and looks at ~/.co once, for everyone
    fd, marker = tempfile.mkstemp(prefix="co-real-home-start-")
    os.close(fd)
    session.config._real_co_start = (time.time_ns(), marker)
    session.config._real_cache_start = _cache_listing()


def _cache_listing():
    """{name: (mtime_ns, size)} of the real REM reader cache, by lstat only."""
    if REAL_REM_CACHE is None or not REAL_REM_CACHE.is_dir():
        return {}
    with os.scandir(REAL_REM_CACHE) as entries:
        return {entry.name: (entry.stat(follow_symlinks=False).st_mtime_ns, entry.stat(follow_symlinks=False).st_size)
                for entry in entries}


def _read_records():
    try:
        with open(_RECORDS, encoding="utf-8") as f:
            rows = sorted({tuple(line.rstrip("\n").split("\t", 2)) for line in f if line.strip()})
    except FileNotFoundError:
        rows = []
    try:
        os.unlink(_RECORDS)
    except FileNotFoundError:
        pass
    return rows


def pytest_sessionfinish(session, exitstatus):
    start = getattr(session.config, "_real_co_start", None)
    if start is None:
        return
    _started_ns, marker = start
    changed = changed_since(marker)
    os.unlink(marker)
    written = _read_records()
    by_us = {os.path.relpath(path, REAL_CO) for _test, _event, path in written}
    others = unexplained(changed, by_us)
    before, after = session.config._real_cache_start, _cache_listing()
    ours = {os.path.basename(path) for _test, _event, path in written}
    others += [("changed", str(REAL_REM_CACHE / name)) for name in sorted(set(before) | set(after))
               if before.get(name) != after.get(name) and name not in ours]
    session.config._real_co_report = {
        "written": written,
        "others": others,
        "rem_turns": _rem_turns(changed) if others else [],
        "processes": _live_co_processes() if others else [],
    }
    if written and session.exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter, config):
    report = getattr(config, "_real_co_report", None)
    if report is None:
        return
    tr = terminalreporter
    if report["written"]:
        tr.section(f"a test wrote the real {REAL_CO} or REM reader cache {REAL_REM_CACHE}", sep="!", red=True, bold=True)
        for test, event, path in report["written"]:
            tr.write_line(f"{test}: {event} {path}")
        tr.write_line("Usually a module-level constant built from Path.home() at import. "
                      "Resolve it at call time, or let _never_touch_the_real_home rebase it.")
    others = report["others"]
    if any(p == "ssh" or p.startswith("ssh" + os.sep) for _label, p in others):
        tr.section(f"{REAL_CO / 'ssh'} CHANGED during this run, not by this pytest", sep="!", yellow=True, bold=True)
        tr.write_line("Nothing in the suite should write there. Check `co server`/`co keys` runs "
                      "and other worktrees' test runs (a branch without 649bebd56 writes ssh/id_ed25519_*).")
    if others:
        tr.section(f"{REAL_CO} changed by another process during the run (not a failure)", sep="-", yellow=True)
        for label, path in others:
            tr.write_line(f"{label}: {path}")
        for path in report["rem_turns"]:
            tr.write_line(f"likely writer: REM turn active in the window: {path}")
        for row in report["processes"][:10]:
            tr.write_line(f"likely writer: live process {row}")
        if len(report["processes"]) > 10:
            tr.write_line(f"likely writer: ... and {len(report['processes']) - 10} more co/codex processes")
    if not report["written"] and not others:
        tr.write_line(f"real-home guard: {REAL_CO} unchanged, no write from this pytest")
    elif not report["written"]:
        tr.write_line(f"real-home guard: no write to {REAL_CO} from this pytest")
