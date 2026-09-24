"""`co browser close` ends every process its daemon owned, or says it did not (#1496).

Playwright starts Chrome in its own process group, so a daemon that died or
hung left the paid runtime running, orphaned, renewing every 15 minutes — and
`close` exited 0. These use real processes: a stand-in daemon that starts a
child in its own session, the way Chrome is started.
"""

import subprocess
import sys
import threading
import time

import psutil
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
    return daemon, psutil.Process(browser_pid)


def test_a_clean_close_exits_0_and_touches_nothing():
    daemon, browser = start(life=0.3, take_browser=True)
    watched = client._process_tree(daemon.pid)

    code, text = client._finish_close(daemon.pid, watched, answered=True,
                                      reason="", payload="Browser closed")

    daemon.wait(5)
    assert (code, text) == (0, "Browser closed")
    assert not browser.is_running()


def test_an_orphaned_browser_is_stopped_and_the_close_exits_1(monkeypatch):
    monkeypatch.setattr(client, "CLOSE_GRACE", 1)
    daemon, browser = start(life=0.3, take_browser=False)
    watched = client._process_tree(daemon.pid)

    code, text = client._finish_close(daemon.pid, watched, answered=True,
                                      reason="", payload="Browser closed")

    daemon.wait(5)
    assert code == 1
    assert "left processes running" in text and f"[{browser.pid}]" in text
    assert not browser.is_running()


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
    assert not browser.is_running()


def test_a_pid_reused_by_another_process_is_not_touched():
    """is_running() checks creation time: a recycled pid is a different process."""
    daemon, browser = start(life=0.1, take_browser=True)
    watched = client._process_tree(daemon.pid)
    daemon.wait(5)
    time.sleep(0.2)

    assert all(not p.is_running() for p in watched)
