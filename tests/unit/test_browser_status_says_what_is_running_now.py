"""`co browser status` says what is running now, not only what ran last (#1473).

"Last command: scroll 3 · 2m ago" leaves the caller to guess whether that
scroll is still going. A caller deciding between "wait" and "restart the
daemon" needs "Busy: scroll 3 on tab lidaily-0700, running 47s".
"""

import time

import pytest

from connectonion.cli.browser_agent import daemon as daemon_module


class _StubBrowser:
    _headless = False

    def __init__(self, tab_meta):
        self._tab_meta = tab_meta

    def _context_is_alive(self):
        return True

    def tab_status(self):
        return "Tabs: none"


@pytest.fixture
def status_of(monkeypatch):
    monkeypatch.setattr(daemon_module, "driver_stealth_status", lambda: ("ok", "1.61.2", "ok"))
    monkeypatch.setattr(daemon_module, "installed_browser_path", lambda: "/bin/chrome")

    def _render(tab_meta, last_command):
        server = daemon_module.BrowserDaemon.__new__(daemon_module.BrowserDaemon)
        server.browser = _StubBrowser(tab_meta)
        server.last_command = last_command
        ok, text = server._status()
        assert ok
        return text

    return _render


def test_a_command_in_flight_is_named_with_its_tab_and_age(status_of):
    started = time.time() - 47
    meta = {"lidaily-0700": {"active_requests": {"r1": {"caller": "lidaily", "line": "scroll 3",
                                                         "started_at": started}}}}

    text = status_of(meta, {"line": "scroll 3", "at": started})

    assert 'Busy: "scroll 3" on tab lidaily-0700, running 47s' in text
    assert "Idle" not in text


def test_the_main_tab_is_called_main(status_of):
    meta = {None: {"active_requests": {"r1": {"caller": "", "line": "go_to https://x.test",
                                               "started_at": time.time() - 5}}}}

    assert 'on tab main, running 5s' in status_of(meta, None)


def test_with_nothing_running_it_says_idle_and_the_last_command(status_of):
    meta = {"lidaily-0700": {"who": "lidaily"}}

    text = status_of(meta, {"line": "scroll 3", "at": time.time() - 120})

    assert 'Idle. Last command: "scroll 3" · 2m ago' in text
    assert "Busy" not in text


def test_two_busy_tabs_share_one_busy_line(status_of):
    now = time.time()
    meta = {"a": {"active_requests": {"r1": {"caller": "a", "line": "scroll 3", "started_at": now - 10}}},
            "b": {"active_requests": {"r2": {"caller": "b", "line": "click x", "started_at": now - 3}}}}

    text = status_of(meta, None)

    assert text.count("Busy:") == 1
    assert '"scroll 3" on tab a, running 10s; "click x" on tab b, running 3s' in text
