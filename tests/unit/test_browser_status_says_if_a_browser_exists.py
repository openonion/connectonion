"""`co browser status` reports the package, not whether a browser can launch.

The previous commit gave `co doctor` a `Browser binary` row for exactly this, and
left `co browser status` as it was — the same decision made in one of the two
places that state it. That is the failure family this release keeps repeating,
and this time it was my own change that split it.

It matters more here than in doctor. `co browser status` is the command that
produced the misleading answer in the first place, on the real deployed nw-map
agent:

    $ co call 0xcf1619cb… co browser status
    Browser: not open · headless=false
    Stealth driver: ✓ patchright 1.61.2 — stealth patches present

    $ co call 0xcf1619cb… co browser go_to https://example.com
    Error: Executable doesn't exist at .../chromium-1228/chrome-linux64/chrome

and it is what the real-API server e2e asserts on
(tests/e2e/real_api/test_server_lifecycle.py::test_the_remote_browser_answers
checks for "Stealth driver" in the output), so that test would pass against a
freshly provisioned server with no browser on it at all.

Cost: this adds a patchright driver start (a few hundred ms) to `status`. That is
the right trade for a command a human runs to find out what is wrong, and the
wrong one for the page commands — which is why the client keys on the daemon's
own launch failure instead.
"""

import pytest

from connectonion.cli.browser_agent import daemon as daemon_module


class _StubBrowser:
    """Only what _status touches."""

    _headless = False

    def _context_is_alive(self):
        return False

    def tab_status(self):
        return "Tabs: none"


@pytest.fixture
def status_text(monkeypatch):
    # Patched on the daemon, not on the browser module: the daemon binds both
    # names at import time, so a patch applied to the source module never
    # reaches it. The first version of this fixture patched browser_module and
    # passed anyway — off the real driver installed on this machine, measuring
    # nothing.
    monkeypatch.setattr(daemon_module, "driver_stealth_status",
                        lambda: ("ok", "1.61.2", "stealth patches present"))
    monkeypatch.setattr(daemon_module, "_daemon_account", lambda: None, raising=False)

    def _render():
        server = daemon_module.BrowserDaemon.__new__(daemon_module.BrowserDaemon)
        server.browser = _StubBrowser()
        server.last_command = None
        ok, text = server._status()
        assert ok
        return text

    return _render


class TestAMissingBrowserIsVisible:

    def test_it_says_none_is_installed(self, status_text, monkeypatch):
        monkeypatch.setattr(daemon_module, "installed_browser_path", lambda: None)

        assert "none installed" in status_text()

    def test_it_names_the_fix(self, status_text, monkeypatch):
        monkeypatch.setattr(daemon_module, "installed_browser_path", lambda: None)

        assert "patchright install chromium" in status_text()

    def test_the_stealth_line_is_not_the_only_green_thing(self, status_text, monkeypatch):
        """The bug was a ✓ standing alone. It may stay — it is true about the
        package — as long as it is not the whole answer."""
        monkeypatch.setattr(daemon_module, "installed_browser_path", lambda: None)
        text = status_text()

        assert "✓ patchright" in text
        assert "✗" in text


class TestAnInstalledBrowserIsNamed:

    PATH = "/home/co/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"

    def test_the_path_is_shown(self, status_text, monkeypatch):
        monkeypatch.setattr(daemon_module, "installed_browser_path", lambda: self.PATH)

        assert self.PATH in status_text()

    def test_nothing_is_reported_missing(self, status_text, monkeypatch):
        monkeypatch.setattr(daemon_module, "installed_browser_path", lambda: self.PATH)

        assert "none installed" not in status_text()


class TestStatusStillAnswersWhenThingsAreBroken:
    """`status` is what you run when the browser is already misbehaving. It must
    not be the command that raises."""

    def test_a_driver_that_cannot_answer_does_not_break_status(self, status_text, monkeypatch):
        def explode():
            raise RuntimeError("driver did not start")

        monkeypatch.setattr(daemon_module, "installed_browser_path", explode)

        assert "Browser:" in status_text()

    def test_the_rest_of_the_report_survives(self, status_text, monkeypatch):
        def explode():
            raise RuntimeError("driver did not start")

        monkeypatch.setattr(daemon_module, "installed_browser_path", explode)
        text = status_text()

        assert "Tabs:" in text
        assert "Last command" in text
