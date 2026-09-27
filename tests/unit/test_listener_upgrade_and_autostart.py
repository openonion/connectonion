"""A listener runs the installed code, and sending starts one (#1859, #1860).

The owner's WhatsApp listener ran from 2026-09-21 through six releases; the
media download merged on the 22nd never ran for it, so no photo anyone sent
was saved, while `check` said all was well. And 5 of their 7 failed sends were
a 30-second wait for a listener nobody had started, although `receive` starts
one by itself.
"""

import json
import signal
from types import SimpleNamespace

import pytest

from connectonion.cli.commands import listen_commands as lc
from connectonion.inbox.store import Inbox


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))


class Provider:
    via_listener = True
    ran = False

    def missing(self):
        return []

    def listen_requirements(self):
        return []

    def run(self, inbox, raw=False):
        # What a new listener has written by the time it is connected.
        self.recorded = json.loads(inbox.listener_file.read_text())

    def render(self, text):
        return text

    def send(self, chat, text, **kw):
        return "3EBSENT"


def test_a_listener_records_the_version_it_runs(monkeypatch):
    p = Provider()
    monkeypatch.setattr(lc, "provider", lambda name: p)
    monkeypatch.setattr(lc, "running_version", lambda: "1.8.9b15")
    lc.handle_listen("whatsapp")
    assert p.recorded["version"] == "1.8.9b15" and isinstance(p.recorded["pid"], int)


@pytest.mark.parametrize("installed, in_flight, restarts", [
    ("1.8.9b16", False, True),     # upgraded, idle: restart into the new code
    ("1.8.9b15", False, False),    # same version: nothing to do
    ("1.8.9b16", True, False),     # a send is in flight: wait for the next sweep
    (None, False, False),          # cannot read the installed version: leave it running
])
def test_a_listener_restarts_itself_after_an_upgrade_only_when_idle(monkeypatch, installed, in_flight, restarts):
    inbox = Inbox("whatsapp")
    if in_flight:
        (inbox.root / "outbox").mkdir(parents=True, exist_ok=True)
        (inbox.root / "outbox" / "1-abc.taken").write_text("{}")
    calls = []
    monkeypatch.setattr(lc.sys, "argv", ["/usr/local/bin/co", "whatsapp", "listen", "--restart"])
    lc.restart_if_upgraded(inbox, running="1.8.9b15", installed=installed,
                           execv=lambda exe, argv: calls.append(argv))
    if restarts:
        [argv] = calls
        assert argv[-2:] == ["whatsapp", "listen"] and "--restart" not in argv
        assert "installed 1.8.9b16, running 1.8.9b15: restarting" in inbox.logfile.read_text()
    else:
        assert calls == []


def test_check_names_both_versions_while_they_differ():
    inbox = Inbox("whatsapp")
    inbox.listener_file.parent.mkdir(parents=True, exist_ok=True)
    inbox.listener_file.write_text(json.dumps({"pid": 4242, "version": "1.8.9b13"}))
    line = lc.version_line("whatsapp", inbox, 4242, installed="1.8.9b15")
    assert "1.8.9b13" in line and "1.8.9b15" in line and "co whatsapp listen --restart" in line
    assert lc.version_line("whatsapp", inbox, 4242, installed="1.8.9b13") == ""


def test_check_says_when_a_listener_predates_version_tracking():
    inbox = Inbox("whatsapp")
    line = lc.version_line("whatsapp", inbox, 50364, installed="1.8.9b15")
    assert "before version tracking" in line and "co whatsapp listen --restart" in line


def test_listen_restart_stops_the_old_listener_and_starts_one_in_the_background(monkeypatch, capsys):
    monkeypatch.setattr(lc, "provider", lambda name: Provider())
    held = iter([50364, 50364, None])
    monkeypatch.setattr(Inbox, "listener_pid", lambda self: next(held, None))
    killed, started = [], []
    monkeypatch.setattr(lc.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, settle=0.0: started.append(settle) or 60001)
    monkeypatch.setattr(lc.time, "sleep", lambda s: None)
    lc.handle_listen("whatsapp", restart=True)
    assert killed == [(50364, signal.SIGTERM)] and started
    assert "60001" in capsys.readouterr().out


def test_send_starts_the_background_listener_when_none_runs(monkeypatch, capsys):
    p = Provider()
    monkeypatch.setattr(lc, "provider", lambda name: p)
    monkeypatch.setattr(Inbox, "listener_pid", lambda self: None)
    started = []
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, settle=0.0: started.append(True) or 60002)
    lc.handle_send("whatsapp", "447700900123@s.whatsapp.net", "on my way")
    assert started == [True]
    assert capsys.readouterr().out.strip() == "3EBSENT"
