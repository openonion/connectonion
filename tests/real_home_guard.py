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
- A manifest of the real ~/.co by lstat() only (never opening a file; ~/.co/ssh
  holds private keys), taken by the controller at start and end. It sees every
  writer, including the operator's own: scheduled REM rounds, token refresh in
  keys.env, mail stores, another worktree's test run. A change it sees with no
  matching record is printed as "changed by another process" and does not fail:
  a guard that goes red whenever the machine is busy is a guard people learn to
  ignore. A change under ssh/ is printed loudly, but is not a failure either --
  `co server new` and `co keys` legitimately write there, and a test's
  subprocess (invisible to the hook) is indistinguishable from them by stat.

CONNECTONION_TEST_REAL_HOME points both at a scratch home for the guard's own
red-first check; nothing else should set it.
"""

import os
import pwd
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
REAL_CO = Path(os.environ.get("CONNECTONION_TEST_REAL_HOME") or pwd.getpwuid(os.getuid()).pw_dir) / ".co"
# Module constants froze whatever $HOME was at import; conftest rebases from here.
IMPORT_CO = Path(os.environ.get("CONNECTONION_TEST_REAL_HOME") or os.path.expanduser("~")) / ".co"
_PREFIXES = tuple({str(REAL_CO), os.path.realpath(REAL_CO)})

# Left out of the manifest because they are large and churn constantly (the
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
    if ".co" not in text:  # the cheap test first; this runs on every open
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


# ---- the manifest ------------------------------------------------------------

def manifest():
    """{relative path: (kind, size, mtime_ns, inode)} of the real ~/.co, by lstat only."""
    found = {}
    if not REAL_CO.is_dir():
        return found
    for root, dirs, files in os.walk(REAL_CO):
        if root == str(REAL_CO):
            dirs[:] = [d for d in dirs if d not in _NOT_IN_MANIFEST]
            files = [f for f in files if f not in _NOT_IN_MANIFEST]
        for name in files + dirs:
            try:
                st = os.lstat(os.path.join(root, name))
            except FileNotFoundError:
                continue  # removed between the listing and the stat
            except PermissionError:
                continue  # an entry another sandbox made unreadable to us; nothing to compare
            rel = os.path.relpath(os.path.join(root, name), REAL_CO)
            found[rel] = ("dir" if name in dirs else "file", st.st_size, st.st_mtime_ns, st.st_ino)
    return found


def _comparable(entry):
    # A directory's mtime moves whenever an entry is added; the entries are in
    # the manifest themselves, so a directory counts only as existing.
    return entry[:1] if entry[0] == "dir" else entry


def diff(before, after):
    """[(created|changed|deleted, relative path)] between two manifests."""
    created = sorted(after.keys() - before.keys())
    changed = sorted(p for p in before.keys() & after.keys() if _comparable(before[p]) != _comparable(after[p]))
    deleted = sorted(before.keys() - after.keys())
    return [("created", p) for p in created] + [("changed", p) for p in changed] + [("deleted", p) for p in deleted]


# ---- naming the other writer -------------------------------------------------

def _rem_turns_in_window(after, started_ns):
    """REM `.state/turns` entries whose mtime falls inside the run, from the manifest."""
    return sorted(p for p, entry in after.items()
                  if p.startswith("rem") and f"{os.sep}.state{os.sep}turns{os.sep}" in os.sep + p
                  and entry[2] >= started_ns)


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
    if not hasattr(session.config, "workerinput"):
        session.config._real_co_start = (time.time_ns(), manifest())


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
    started_ns, before = start
    after = manifest()
    written = _read_records()
    by_us = {os.path.relpath(path, REAL_CO) for _test, _event, path in written}
    others = [(label, p) for label, p in diff(before, after) if p not in by_us]
    session.config._real_co_report = {
        "written": written,
        "others": others,
        "rem_turns": _rem_turns_in_window(after, started_ns) if others else [],
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
        tr.section(f"a test wrote the real {REAL_CO}", sep="!", red=True, bold=True)
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
