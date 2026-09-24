"""`co browser close` ends every process its daemon owned, or says it did not (#1496).

Playwright starts Chrome in its own process group, so a daemon that died or
hung left the paid runtime running, orphaned, renewing every 15 minutes — and
`close` exited 0. These use real processes: a stand-in daemon that starts a
child in its own session, the way Chrome is started.
"""

import os
import subprocess
import sys
import threading
import time

import pytest

from connectonion.cli.browser_agent import client

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX sessions")

# A "daemon" that starts a "browser" in a new session and prints its pid, then
# either exits after `life` seconds (leaving or taking the browser) or never.
DAEMON = """
import subprocess, sys, time
browser = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                           start_new_session=True)
print(browser.pid, flush=True)
life, take_browser = float(sys.argv[1]), sys.argv[2] == "take"
time.sleep(life)
if take_browser:
    browser.terminate(); browser.wait()
"""


def start(life, take_browser):
    daemon = subprocess.Popen([sys.executable, "-c", DAEMON, str(life),
                               "take" if take_browser else "leave"],
                              stdout=subprocess.PIPE, text=True)
    browser_pid = int(daemon.stdout.readline())
    # The real daemon is detached, so it never becomes the CLI's zombie. This one
    # is our child: reap it the moment it exits, or it counts as still running.
    threading.Thread(target=daemon.wait, daemon=True).start()
    return daemon, browser_pid


def running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def gone(pid, within=5.0):
    deadline = time.monotonic() + within
    while running(pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    return not running(pid)


def test_a_clean_close_exits_0_and_touches_nothing():
    daemon, browser = start(life=0.3, take_browser=True)
    watched = client._process_tree(daemon.pid)

    code, text = client._finish_close(daemon.pid, watched, answered=True,
                                      reason="", payload="Browser closed")

    daemon.wait(5)
    assert (code, text) == (0, "Browser closed")
    assert gone(browser)


def test_an_orphaned_browser_is_stopped_and_the_close_exits_1(monkeypatch):
    monkeypatch.setattr(client, "CLOSE_GRACE", 1)
    daemon, browser = start(life=0.3, take_browser=False)
    watched = client._process_tree(daemon.pid)

    code, text = client._finish_close(daemon.pid, watched, answered=True,
                                      reason="", payload="Browser closed")

    daemon.wait(5)
    assert code == 1
    assert "left processes running" in text and f"[{browser}]" in text
    assert gone(browser)


def test_a_daemon_that_never_answers_is_ended_with_its_browser(monkeypatch):
    monkeypatch.setattr(client, "CLOSE_GRACE", 1)
    monkeypatch.setattr(client, "_wait_for_pid_exit", lambda pid, timeout=15.0: False)
    daemon, browser = start(life=600, take_browser=False)
    watched = client._process_tree(daemon.pid)

    code, text = client._finish_close(daemon.pid, watched, answered=False,
                                      reason="no answer within 60s")

    daemon.wait(10)
    assert code == 1 and "did not answer" in text
    assert daemon.returncode is not None
    assert gone(browser)


def test_a_live_pid_with_another_start_time_is_a_different_process():
    """Identity is pid and start time: a pid the OS gave to something else later
    must never be treated as one of the browser's processes."""
    me = client._process_tree(os.getpid())[0]
    recycled = client._Proc(me.pid, "Mon Jan  1 00:00:00 2001", me.name)

    assert client._still_running([me]) == [me]
    assert client._still_running([recycled]) == []


def test_the_tree_includes_a_child_in_its_own_session():
    """The whole point: Chrome is started in its own process group."""
    daemon, browser = start(life=600, take_browser=True)
    try:
        pids = {p.pid for p in client._process_tree(daemon.pid)}
        assert {daemon.pid, browser} <= pids
    finally:
        daemon.kill()
        os.kill(browser, 9)
