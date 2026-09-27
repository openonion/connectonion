"""A background listener loads the installed package, and restarts at most once per upgrade (#1878).

b16's real end-to-end run started `co whatsapp listen --restart` from inside a
connectonion checkout. The listener is `python -m connectonion.cli.main`, and
`-m` puts the working directory first on sys.path, so it ran the checkout's
code (1.8.9b17) while 1.8.9b16 was installed. Its self-restart would have
landed in the same checkout every minute.
"""

import json
from types import SimpleNamespace

import pytest

from connectonion.cli.commands import listen_commands as lc
from connectonion.inbox import store
from connectonion.inbox.store import Inbox


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))


def test_the_background_listener_starts_in_the_inbox_directory(monkeypatch):
    started = {}

    class Exited:
        pid = 4242

        def poll(self):
            return 1

    def popen(argv, **kwargs):
        started.update(kwargs)
        return Exited()
    monkeypatch.setattr(store.subprocess, "Popen", popen)
    inbox = Inbox("whatsapp")
    inbox.ensure_listener()
    assert started["cwd"] == str(inbox.root)


def test_a_restart_runs_from_the_inbox_directory(monkeypatch):
    inbox = Inbox("whatsapp")
    moved = []
    monkeypatch.setattr(lc.os, "chdir", lambda path: moved.append(str(path)))
    lc.restart_if_upgraded(inbox, running="1.8.9b16", installed="1.8.9b17", execv=lambda *a: None)
    assert moved == [str(inbox.root)]


def test_a_restart_for_the_same_installed_version_happens_once(monkeypatch):
    inbox = Inbox("whatsapp")
    monkeypatch.setattr(lc.os, "chdir", lambda path: None)
    calls = []
    for _ in range(3):
        lc.restart_if_upgraded(inbox, running="1.8.9b17", installed="1.8.9b16",
                               execv=lambda exe, argv: calls.append(argv))
    assert len(calls) == 1
    log = inbox.logfile.read_text()
    assert "not restarting again" in log and log.count("not restarting again") == 1


def test_a_newer_install_after_that_is_restarted_for(monkeypatch):
    inbox = Inbox("whatsapp")
    monkeypatch.setattr(lc.os, "chdir", lambda path: None)
    calls = []
    lc.restart_if_upgraded(inbox, running="1.8.9b17", installed="1.8.9b16", execv=lambda e, a: calls.append(1))
    lc.restart_if_upgraded(inbox, running="1.8.9b17", installed="1.8.9b18", execv=lambda e, a: calls.append(1))
    assert len(calls) == 2
