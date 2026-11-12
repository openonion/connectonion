"""No test run leaves a co ai Host behind.

`co rem open` starts the reader's Host detached (its own session), so it outlives
the test that started it, pytest and the terminal. Three were found on a laptop
two days after the run that started them and five on another machine, each a
whole co ai under a pytest temp home (#2937).

Two layers:
- after each test, the Host recorded in that test's own home is stopped;
- when the session ends, a Host still alive under this run's temp directory
  fails the run, naming the test that started it, and is stopped.

Whether a process is ours to stop is read from the process, never from a record:
tests write records with invented pids, and a pid can be given to something
else. It is stopped only when its user is ours, its command is the reader's Host
command and its HOME is under this pytest run's temp directory. A Host on the
developer's real home is never listed, so never signalled.
"""

import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

import pytest

# The tail live_host._spawn gives the reader's Host; a hand-run `co ai` has no such tail.
_HOST = re.compile(r" ai --port \d+ --no-listen --no-launch(?= |$)")
_HOME = re.compile(r"(?:^| )HOME=(\S+)")
_TEST = re.compile(r"(?:^| )PYTEST_CURRENT_TEST=(.*?)(?= [A-Za-z_][A-Za-z0-9_]*=|$)")


def hosts_under(root: Path, pids=None) -> list:
    """[(pid, home, test)]: this user's reader Hosts whose HOME is under `root`.

    The environment is the one the process was started with: /proc where there
    is one (Linux), else what `ps e` prints after the command (macOS, where it
    shows only the caller's own processes, which is all that is wanted).
    """
    if os.name == "nt":  # no ps; nothing detaches the same way there
        return []
    # One BSD-style word: macOS takes a second word ("ax") for an argument.
    which = ["eww", "-p", ",".join(str(pid) for pid in pids)] if pids else ["axeww"]
    result = subprocess.run(["ps", *which, "-o", "pid=", "-o", "uid=", "-o", "command="],
                            capture_output=True, text=True, timeout=30)
    # A failing or empty ps is not "no Hosts": the guard would report a clean run.
    # Every process listed is never empty (this one is in it); pids that have all
    # exited print nothing and exit 1 with nothing on stderr.
    gone = pids and result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip()
    if not gone and (result.returncode != 0 or not result.stdout.strip()):
        raise RuntimeError(f"ps could not list processes (exit {result.returncode}): {result.stderr.strip()}")
    listing = result.stdout
    root, found = os.path.realpath(root), []
    for line in listing.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) < 3 or fields[1] != str(os.getuid()) or not _HOST.search(fields[2]):
            continue
        try:
            environment = Path(f"/proc/{fields[0]}/environ").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            environment = fields[2]
        home = _HOME.search(environment)
        if home and os.path.realpath(home.group(1)).startswith(root + os.sep):
            test = _TEST.search(environment)
            found.append((int(fields[0]), home.group(1), test.group(1) if test else "unknown test"))
    return found


def stop(root: Path, pid: int) -> None:
    """End one Host, checked again before each signal: the pid is still that Host."""
    for sign, wait in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 5.0)):
        if not hosts_under(root, [pid]):
            return
        try:
            os.kill(pid, sign)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and hosts_under(root, [pid]):
            time.sleep(0.05)


def stop_recorded(root: Path, home: str) -> None:
    """Stop the Host that a test's own home recorded, if one is running."""
    # Only a home of this run is read: a real_api test keeps the developer's.
    if not home or not os.path.realpath(home).startswith(os.path.realpath(root) + os.sep):
        return
    try:
        pid = json.loads((Path(home) / ".co" / "rem-live-host.json").read_text()).get("pid")
    except (OSError, ValueError, AttributeError):
        return
    if isinstance(pid, int) and pid > 0:
        stop(root, pid)


class HostLeakGuard:
    """Registered as a plugin object: conftest already takes these hook names
    from real_home_guard, and a module can hold one function per name."""

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(self, item):
        """After every fixture is undone, not as a fixture: a test that replaced
        Path.read_text or subprocess.run with one that fails still has it in
        place while fixtures finish, and six tests errored in teardown that way."""
        home = os.environ.get("HOME")   # the test's own, before its fixtures give the runner's back
        yield
        stop_recorded(item.config._tmp_path_factory.getbasetemp(), home)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        if hasattr(session.config, "workerinput"):
            return  # the controller looks once, after every worker has finished
        # xdist hands each worker a folder under this one, so it covers them all.
        root = session.config._tmp_path_factory.getbasetemp()
        leaked = hosts_under(root)
        for pid, _home, _test in leaked:
            stop(root, pid)
        session.config._leaked_hosts = leaked
        if leaked and session.exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter, config):
        leaked = getattr(config, "_leaked_hosts", None)
        if not leaked:
            return
        terminalreporter.section("co ai Hosts left running by this test run", sep="=", red=True, bold=True)
        for pid, home, test in leaked:
            terminalreporter.line(f"pid {pid}  HOME={home}  started by {test}")
        terminalreporter.line("They were stopped. A test that can start the reader's Host must record it in "
                              "its own temp home (tests/host_leak_guard.py), or stop it itself.")
