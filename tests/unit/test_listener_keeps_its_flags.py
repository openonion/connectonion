"""A replacement listener keeps `--raw`, and every exit leaves a line (#1882).

On 2026-09-27 the owner's `co whatsapp listen --raw` in tmux was replaced twice
by a bare background listener: `listen --restart` stopped it without a word in
the log, and started one without `--raw`. The raw archive and real sender names
stopped, and `check` stayed green.
"""

import json
import signal

import pytest

from connectonion.cli.commands import listen_commands as lc
from connectonion.inbox import store
from connectonion.inbox.store import Inbox


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))


class Provider:
    via_listener = True

    def __init__(self, during=None):
        self.during = during

    def missing(self):
        return []

    def listen_requirements(self):
        return []

    def run(self, inbox, raw=False):
        if self.during:
            self.during(inbox)


def test_a_listener_records_the_flags_it_was_started_with(monkeypatch):
    monkeypatch.setattr(lc, "provider", lambda name: Provider())
    lc.handle_listen("whatsapp", raw=True)
    assert json.loads(Inbox("whatsapp").listener_file.read_text())["flags"] == ["--raw"]


def test_an_auto_started_listener_reuses_the_recorded_flags(monkeypatch):
    inbox = Inbox("whatsapp")
    inbox.listener_file.parent.mkdir(parents=True, exist_ok=True)
    inbox.listener_file.write_text(json.dumps({"pid": 1, "version": "x", "flags": ["--raw", "--bogus"]}))
    started = {}

    class Exited:
        pid, returncode = 4242, 1

        def poll(self):
            return 1

    def popen(argv, **kwargs):
        started["argv"] = argv
        return Exited()
    monkeypatch.setattr(store.subprocess, "Popen", popen)
    inbox.ensure_listener()
    assert started["argv"][-3:] == ["whatsapp", "listen", "--raw"]   # only flags listen knows


def test_a_sigterm_leaves_a_line_in_the_log(monkeypatch):
    def terminated(inbox):
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    monkeypatch.setattr(lc, "provider", lambda name: Provider(during=terminated))
    before = signal.getsignal(signal.SIGTERM)
    with pytest.raises(SystemExit):
        lc.handle_listen("whatsapp")
    assert "stopped by SIGTERM" in Inbox("whatsapp").logfile.read_text()
    assert signal.getsignal(signal.SIGTERM) is before   # the handler is put back


def test_listen_restart_names_what_it_stopped_and_where_the_new_one_runs(monkeypatch, capsys):
    monkeypatch.setattr(lc, "provider", lambda name: Provider())
    held = iter([2582, None])
    monkeypatch.setattr(Inbox, "listener_pid", lambda self: next(held, None))
    monkeypatch.setattr(lc.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(Inbox, "ensure_listener", lambda self, settle=0.0: 60001)
    monkeypatch.setattr(lc.time, "sleep", lambda s: None)
    lc.handle_listen("whatsapp", restart=True)
    assert "stopped by listen --restart (pid 2582)" in Inbox("whatsapp").logfile.read_text()
    assert "background" in capsys.readouterr().out
