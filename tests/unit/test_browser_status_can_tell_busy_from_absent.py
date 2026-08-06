"""`co browser status` says "not running" while a daemon is running and busy.

Measured while trying to drive chat.openonion.ai for the release e2e:

    $ co browser status          Browser daemon: not running — the next page
    $ co browser status          command starts one          (three times)
    $ co browser status
    $ co browser go_to https://chat.openonion.ai
      browser daemon is busy (a long command is holding it) — try again
    $ pgrep -f 'user-data-dir=~/.co/browser_profile' | wc -l
      14

So a daemon was holding the endpoint, fourteen Chrome processes were up, and the
one command whose job is to report that said the opposite. A user runs `status`
to find out why their commands fail and is told to expect the next one to start
a browser; every command then answers "busy". The diagnostic points away from
the truth.

#711 was the same disagreement in the other direction — `status` said "open"
about a browser that had died.

## The distinction already exists

status prints its line from the branch where `_connect()` returned None, on the
reasoning recorded there: "With nobody listening the answer is already known."
A failed connect is not nobody listening. The very next code path says so, and
already handles it:

    if _owner_alive(sock_path):
        # A daemon IS running — it just can't take our connection right now
        # (its backlog is full behind a long-running command). "Did not start"
        # would lie.

`_owner_alive` reads the pidfile and asks whether that pid is alive. No spawn,
no `~/.co/browser.log` created — which matters, because #356 is why status must
not start anything: in a sandbox with $HOME readable and writes confined to the
workspace, opening that log raised PermissionError and the CLI printed a
traceback instead of a status.
"""

import pathlib

import pytest


@pytest.fixture
def client(monkeypatch, tmp_path):
    from connectonion.cli.browser_agent import client as mod

    # Nothing is listening — the state both the real cases share.
    monkeypatch.setattr(mod, "_connect", lambda *a, **k: None)
    return mod


def _run_status(client, capsys):
    client.send("status")
    return capsys.readouterr().out


class TestABusyDaemonIsNotReportedAbsent:

    def test_it_does_not_say_not_running(self, client, monkeypatch, capsys):
        monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: True)

        assert "not running" not in _run_status(client, capsys)

    def test_it_says_the_daemon_is_there(self, client, monkeypatch, capsys):
        monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: True)

        assert "busy" in _run_status(client, capsys).lower()

    def test_it_does_not_promise_the_next_command_will_start_one(
        self, client, monkeypatch, capsys
    ):
        """That promise is what sends the user in the wrong direction."""
        monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: True)

        assert "starts one" not in _run_status(client, capsys)


class TestAnAbsentDaemonStillReadsAbsent:

    def test_it_says_not_running(self, client, monkeypatch, capsys):
        monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: False)

        assert "not running" in _run_status(client, capsys)

    def test_it_still_says_the_next_command_starts_one(
        self, client, monkeypatch, capsys
    ):
        monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: False)

        assert "starts one" in _run_status(client, capsys)


class TestStatusStillStartsNothing:
    """#356: asking whether the browser runs must not launch one, and must not
    create ~/.co/browser.log to find out."""

    def test_no_daemon_is_spawned(self, client, monkeypatch, capsys):
        spawned = []
        monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: True)
        monkeypatch.setattr(
            client, "_spawn_daemon", lambda *a, **k: spawned.append(1)
        )

        _run_status(client, capsys)

        assert spawned == []

    def test_nothing_is_provisioned(self, client, monkeypatch, capsys):
        provisioned = []
        monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: False)
        monkeypatch.setattr(
            client, "_ensure_browser_ready", lambda *a, **k: provisioned.append(1)
        )

        _run_status(client, capsys)

        assert provisioned == []

    def test_it_exits_zero_either_way(self, client, monkeypatch, capsys):
        for alive in (True, False):
            monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: alive)

            assert client.send("status") == 0

    def test_it_does_not_create_the_browser_log(self, client, monkeypatch,
                                                tmp_path, capsys):
        """#356 in one assertion: opening that log is what raised
        PermissionError in a sandbox and printed a traceback instead."""
        monkeypatch.setattr(client, "_owner_alive", lambda *a, **k: True)
        monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))

        client.send("status")

        assert not (tmp_path / ".co" / "browser.log").exists()
