"""Asking whether the browser is running does not start it.

`co browser status` goes through the same cold-start path as every other verb:

    conn = _connect(sock_path)
    if conn is None:
        _ensure_browser_ready(line)      # skipped for pageless verbs
        conn = _spawn_daemon(sock_path, headless)

`_spawn_daemon` creates `~/.co/` and opens `~/.co/browser.log` for append before
launching a detached daemon. So the answer to "is the browser running?" is
obtained by starting a browser — which makes the answer yes, and costs a Chrome
process to learn nothing.

Where it stops being merely backwards: a sandbox that can read `$HOME` but write
only to the workspace and temp. The `mkdir`/`open` raise `PermissionError`,
`send()` catches only `RuntimeError`, and the CLI prints a Typer traceback
instead of a status. Reported from a real managed sandbox in #356:

    CO_WHO=codex-root co browser status

With no daemon there is nothing to report but "not running", and that answer
needs no process, no home directory and no log.

The other pageless verbs — `tab`, `use`, `close` — read a registry that lives
inside the daemon, so they are left alone here: they have a reason to want one.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from connectonion.cli.browser_agent import client
from connectonion.network.oip import browser_daemon_pb2 as wire
from connectonion.network.oip.framing import decode_frame, encode_frame


@pytest.fixture
def no_daemon(monkeypatch, tmp_path):
    """A cold start: nothing listening, and a home nobody may write to.

    `_owner_alive` is pinned too. A refused connection alone does not mean no
    daemon — one whose backlog is full behind a long command refuses as well —
    so status now consults the pidfile to tell those apart
    (test_browser_status_can_tell_busy_from_absent). Without pinning it, this
    fixture describes a cold start on a machine that has no browser and a busy
    daemon on one that does, and the file it belongs to is about the cold start.
    """
    monkeypatch.setattr(client, "_connect", lambda *a, **k: None)
    monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: False)

    def refuse(*args, **kwargs):
        raise AssertionError("status spawned a daemon")

    monkeypatch.setattr(client, "_spawn_daemon", refuse)
    return tmp_path


class TestNothingIsStarted:

    def test_status_does_not_spawn_a_daemon(self, no_daemon, capsys):
        code = client.send("status")

        assert code == 0, capsys.readouterr()

    def test_it_says_the_daemon_is_not_running(self, no_daemon, capsys):
        client.send("status")

        out = capsys.readouterr().out
        assert "not running" in out.lower(), out

    def test_it_writes_nothing_under_the_home_directory(self, no_daemon, monkeypatch, tmp_path):
        """The sandbox case: $HOME is readable and not writable."""
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

        client.send("status")

        assert not (home / ".co").exists(), list(home.iterdir())

    def test_a_read_only_home_does_not_raise(self, no_daemon, monkeypatch, tmp_path):
        """What #356 actually saw — a traceback, not an error line."""
        home = tmp_path / "locked"
        home.mkdir()
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
        home.chmod(0o500)
        try:
            assert client.send("status") == 0
        finally:
            home.chmod(0o700)


class TestEverythingElseStillStarts:

    def test_a_page_verb_still_spawns(self, monkeypatch):
        """The fix must not turn the daemon off for the verbs that need it."""
        monkeypatch.setattr(client, "_connect", lambda *a, **k: None)
        monkeypatch.setattr(client, "_ensure_browser_ready", lambda line: None)
        spawned = []

        def record(sock_path, headless):
            spawned.append(sock_path)
            raise RuntimeError("stop here — spawning is what we wanted to see")

        monkeypatch.setattr(client, "_spawn_daemon", record)

        client.send("go_to https://example.com")

        assert spawned, "a page-driving verb no longer starts the daemon"

    def test_tab_still_spawns(self, monkeypatch):
        """`tab` reads a registry that lives in the daemon process."""
        monkeypatch.setattr(client, "_connect", lambda *a, **k: None)
        monkeypatch.setattr(client, "_ensure_browser_ready", lambda line: None)
        spawned = []
        monkeypatch.setattr(client, "_spawn_daemon",
                            lambda s, h: (spawned.append(s), _raise())[0])

        def _raise():
            raise RuntimeError("stop")

        client.send("tab")

        assert spawned


class TestAWarmDaemonIsUnaffected:

    def test_status_reaches_a_running_daemon(self, monkeypatch, capsys):
        """When one is up, status must still ask it — the local answer is only
        for the case where there is nobody to ask.

        The fake reply is delivered once and then the socket reports EOF. An
        earlier version of this returned the same bytes on every recv, so
        send()'s read-to-EOF loop never ended: green here, and a job killed at
        five minutes on CI. A fake that cannot end is not a fake of a socket.
        """
        sent = []

        class FakeConn:
            def __init__(self):
                self._reply = b""

            def sendall(self, data):
                sent.append(data)
                request_id = decode_frame(data).request_id
                self._reply = encode_frame(
                    wire.Envelope(
                        protocol_version=2,
                        request_id=request_id,
                        result=wire.BrowserResult(
                            text="Browser: open, headless=false"
                        ),
                    )
                )

            def shutdown(self, how):
                pass

            def recv(self, n):
                reply, self._reply = self._reply[:n], self._reply[n:]
                return reply

            def close(self):
                pass

        monkeypatch.setattr(client, "_connect", lambda *a, **k: FakeConn())

        code = client.send("status")

        assert sent, "status did not reach the running daemon"
        assert code == 0
        assert "Browser: open" in capsys.readouterr().out
