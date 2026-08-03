"""Who the relay heartbeat is talking to.

Every sixty seconds the relay loop refreshes its ANNOUNCE — the relay drops a
registration after about 120 seconds of silence — and prints a `♥`. In a
terminal that is a pulse you can watch. Under systemd it is a line in the
journal, and measured on a live agent it is most of the journal:

    11 hours of logs      3656 lines
    heartbeats            ~660 of them
    the rest              mostly one repeated failure banner

1400 lines a day that say nothing, on every deployed agent, drowning the ones
that do. "Is it running" is already answered by `systemctl status`.

This repo already draws the line where it belongs — connectonion/__init__.py:

    _show_env = _sys.stderr.isatty() or _os.getenv("CO_DEBUG_ENV") == "1"

with the reasoning that a redirected stream is a different audience. The
heartbeat is the same shape: decoration for a person watching, noise in a file.

Everything that is not a heartbeat still prints either way — `♥ cannot refresh`,
`Relay error`, `Relay disconnected`. Silence means healthy, which is what a log
is for.
"""

import inspect

import pytest

from connectonion.network import relay
from connectonion.network.relay import heartbeat_is_worth_printing


class TestATerminalSeesIt:

    def test_an_attached_terminal_gets_the_pulse(self, monkeypatch):
        monkeypatch.setattr('sys.stderr.isatty', lambda: True, raising=False)

        assert heartbeat_is_worth_printing() is True


class TestAJournalDoesNot:

    def test_a_redirected_stream_stays_quiet(self, monkeypatch):
        monkeypatch.setattr('sys.stderr.isatty', lambda: False, raising=False)

        assert heartbeat_is_worth_printing() is False

    def test_it_can_be_turned_back_on(self, monkeypatch):
        """The same escape hatch as CO_DEBUG_ENV: someone debugging a piped run
        should be able to ask for it."""
        monkeypatch.setattr('sys.stderr.isatty', lambda: False, raising=False)
        monkeypatch.setenv('CO_HEARTBEAT', '1')

        assert heartbeat_is_worth_printing() is True


class TestOnlyTheHeartbeatIsAffected:
    """The failure lines are the reason the log exists at all."""

    def _line_containing(self, text: str) -> str:
        source = inspect.getsource(relay)
        return next(l for l in source.splitlines() if text in l)

    def test_the_lapse_warning_is_unconditional(self):
        assert 'heartbeat_is_worth_printing' not in self._line_containing('cannot refresh')

    def test_relay_errors_are_unconditional(self):
        assert 'heartbeat_is_worth_printing' not in self._line_containing('Relay error:')
