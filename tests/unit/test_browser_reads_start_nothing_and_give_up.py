"""Reading the browser neither starts one nor waits on a frozen one, and a forced close cleans up.

Found by the final tester on 1.8.8b11, with CO_BROWSER_SOCK pointing at a
scratch socket:

- `co browser tab ls` with nothing running started a headed daemon to list no
  tabs; the `--headless` command after it was then ignored with a note.
- With the daemon frozen by `kill -STOP`, `get_current_url` took 151 s while
  the notes promised every command ends within 120 s (or its --timeout + 15),
  and `status` gave up at 30 s.
- The forced `close` of that frozen daemon left b.sock, b.sock.pid (naming the
  dead pid) and b.sock.lock behind.
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from connectonion.cli.browser_agent import client
from connectonion.cli.browser_agent import transport


@pytest.fixture
def short_dir():
    directory = tempfile.mkdtemp(prefix="cor")  # AF_UNIX paths are capped near 104 bytes
    yield Path(directory)
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def nothing_running(short_dir, monkeypatch):
    monkeypatch.setenv("CO_BROWSER_SOCK", str(short_dir / "none.sock"))

    def must_not_spawn(*_args, **_kwargs):
        raise AssertionError("a daemon was started to read a browser that is not open")

    monkeypatch.setattr(client, "_spawn_daemon", must_not_spawn)
    monkeypatch.setattr(client, "_ensure_browser_ready", must_not_spawn)


# ---- tab ls with nothing running ---------------------------------------------------

@pytest.mark.parametrize("line", ["tab ls", "tab list"])
def test_tab_ls_with_no_daemon_lists_nothing_and_starts_nothing(line, nothing_running):
    code, payload = client._request_with_identity(line, caller="c", account="")

    assert code == 0
    assert "no browser is open" in payload.lower() and "go_to" in payload


def test_tab_ls_json_with_no_daemon_is_an_empty_list(nothing_running):
    assert client._request_with_identity("tab ls --json", caller="c", account="") == (0, "[]")


def test_tab_close_with_no_daemon_has_nothing_to_close(nothing_running):
    code, payload = client._request_with_identity("tab close X", caller="c", account="")

    assert code == 0 and "nothing to close" in payload


# ---- deadlines -------------------------------------------------------------------------

def test_an_ordinary_command_waits_for_the_daemons_deadline_not_150_seconds():
    assert client._reply_deadline(["go_to", "https://example.com"]) == 130
    assert client._reply_deadline(["wait_for_element", "#x", "--timeout", "200"]) == 225
    assert client._reply_deadline(["status"]) == client.QUICK_REPLY_DEADLINE


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX socket")
def test_a_read_against_a_frozen_daemon_gives_up_when_status_would(short_dir, monkeypatch):
    sock = str(short_dir / "b.sock")
    monkeypatch.setenv("CO_BROWSER_SOCK", sock)
    monkeypatch.setattr(client, "LIVENESS_WINDOW", 0.3)
    monkeypatch.setattr(client, "QUICK_REPLY_DEADLINE", 0.5)
    # kill -STOP: the kernel still accepts the connection; nothing ever answers.
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(sock)
    listener.listen(8)
    Path(sock + ".pid").write_text(str(os.getpid()), encoding="utf-8")
    try:
        started = time.monotonic()
        code, payload = client._request_with_identity("get_current_url", caller="t", account="")
        assert time.monotonic() - started < 10
        assert code == 1
        assert "stopped or stuck" in payload and "co browser close" in payload
    finally:
        listener.close()


class _Conn:
    def __init__(self):
        self.timeouts = []

    def settimeout(self, value):
        self.timeouts.append(value)


def test_a_read_behind_a_busy_tab_keeps_waiting_while_status_answers(monkeypatch):
    monkeypatch.setattr(client, "LIVENESS_WINDOW", 0.01)
    silent = iter([TimeoutError(), TimeoutError(), "the answer"])

    def receive():
        value = next(silent)
        if isinstance(value, Exception):
            raise value
        return value

    probes = []
    answer = client._answer_while_alive(receive, _Conn(), 60, alive=lambda: probes.append(1) or True)

    assert answer == "the answer" and len(probes) == 2


# ---- a forced close leaves nothing behind -------------------------------------------------

def _stuck_daemon():
    """A process standing in for a frozen daemon, reaped when it dies so ps
    does not keep listing it as a zombie."""
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    reaper = threading.Thread(target=process.wait, daemon=True)
    reaper.start()
    return process, reaper


def _sidecars(sock: str, pid: int):
    Path(sock).write_text("")
    Path(transport.pid_path(sock)).write_text(str(pid), encoding="utf-8")
    Path(transport.lock_path(sock)).write_text("")
    return [sock, transport.pid_path(sock), transport.lock_path(sock)]


@pytest.mark.skipif(sys.platform == "win32", reason="ps and POSIX sidecars")
def test_a_forced_close_removes_the_socket_pidfile_and_lock(short_dir):
    process, reaper = _stuck_daemon()
    os.kill(process.pid, signal.SIGSTOP)
    files = _sidecars(str(short_dir / "b.sock"), process.pid)
    try:
        code, payload = client._finish_close(process.pid, client._process_tree(process.pid), answered=False,
                                             reason="no answer", sock_path=files[0])
    finally:
        process.kill()
        reaper.join(timeout=10)

    assert code == 1 and "by force" in payload
    assert [f for f in files if os.path.exists(f)] == []


@pytest.mark.skipif(sys.platform == "win32", reason="ps and POSIX sidecars")
def test_a_replacement_daemons_files_are_left_alone(short_dir):
    process, reaper = _stuck_daemon()
    files = _sidecars(str(short_dir / "b.sock"), os.getpid())  # someone else wrote the pidfile since
    try:
        client._finish_close(process.pid, client._process_tree(process.pid), answered=False,
                             reason="no answer", sock_path=files[0])
    finally:
        process.kill()
        reaper.join(timeout=10)

    assert all(os.path.exists(f) for f in files)
