"""`co doctor` reports the browser package and calls it healthy with no browser.

The Browser panel checks `driver_stealth_status()`, which reads the installed
patchright package. Nothing checks whether a browser binary exists. On the real
deployed nw-map agent:

    $ co call 0xcf1619cb… co browser status
    Stealth driver: ✓ patchright 1.61.2 — stealth patches present

    $ co call 0xcf1619cb… co browser go_to https://example.com
    Error: Executable doesn't exist at
    /home/co/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome

`co doctor` on that box prints "Patchright ✓ / Stealth driver ✓" and ends with
"✅ Diagnostics complete — nothing wrong". Every browser command fails. This is
the command whose whole job is to say what is wrong.

The check asks patchright, rather than guessing: `chromium.executable_path` is
computed by patchright itself, including the version-numbered directory
(chromium-1228) that a hand-written probe would get wrong on their next release.
Measured both ways on Linux:

    executable_path: /home/…/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome
    exists: True
    PLAYWRIGHT_BROWSERS_PATH=/tmp/empty-browsers → exists: False

It costs starting the driver (a few hundred ms), which is why the browser client
uses the daemon's own launch failure instead — free, and it arrives exactly when
it matters. For doctor, which already makes network calls, a one-off is fine.
"""

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app


runner = CliRunner()


# doctor imports these inside the function, so the binding is looked up on the
# browser module at call time — patching doctor_commands would be ignored, and a
# test that patched the wrong module would pass while measuring nothing.
import connectonion.useful_tools.browser_tools.browser as browser_module


@pytest.fixture
def stealth_ok(monkeypatch):
    """A healthy package, which is all doctor used to look at."""
    monkeypatch.setattr(browser_module, "driver_stealth_status",
                        lambda: ("ok", "1.61.2", "stealth patches present"))


def _run():
    return runner.invoke(app, ["doctor"], env={"COLUMNS": "200"}).output


class TestAMissingBrowserIsReported:

    @pytest.fixture(autouse=True)
    def no_browser(self, monkeypatch, stealth_ok):
        monkeypatch.setattr(browser_module, "installed_browser_path", lambda: None)

    def test_the_panel_says_no_browser_is_installed(self):
        output = _run()

        assert "Browser binary" in output

    def test_it_does_not_end_with_nothing_wrong(self):
        """The finding has to reach the verdict, not just the table — a row that
        says ✗ under a green summary is the same lie in smaller type."""
        assert "nothing wrong" not in _run()

    def test_it_names_the_command_that_fixes_it(self):
        assert "patchright install chromium" in _run()


class TestAnInstalledBrowserIsReportedGreen:

    @pytest.fixture(autouse=True)
    def has_browser(self, monkeypatch, stealth_ok):
        monkeypatch.setattr(
            browser_module, "installed_browser_path",
            lambda: "/home/co/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome")

    def test_the_panel_shows_it(self):
        output = _run()

        assert "Browser binary" in output
        assert "chromium-1228" in output or "✓" in output

    def test_nothing_is_reported_wrong(self):
        assert "patchright install chromium" not in _run()


class TestTheProbeItself:
    """installed_browser_path() must answer from patchright, not from a guess."""

    @pytest.fixture(autouse=True)
    def no_desktop_chrome(self, monkeypatch, request):
        """The patchright branch is only reached with no desktop Chrome — and the
        machine these were written on has one, so without this the first two
        tests measured Chrome's path instead of what they patched."""
        if "system_chrome" in request.node.name:
            return
        monkeypatch.setattr(browser_module, "find_system_chrome", lambda: None,
                            raising=False)

    def test_it_returns_none_when_the_path_does_not_exist(self, monkeypatch):
        monkeypatch.setattr(browser_module, "_patchright_chromium_path",
                            lambda: "/nowhere/chromium-9999/chrome", raising=False)

        assert browser_module.installed_browser_path() is None

    def test_it_returns_the_path_when_it_exists(self, monkeypatch, tmp_path):
        fake = tmp_path / "chrome"
        fake.write_text("#!/bin/sh\n")
        monkeypatch.setattr(browser_module, "_patchright_chromium_path",
                            lambda: str(fake), raising=False)

        assert browser_module.installed_browser_path() == str(fake)

    def test_a_system_chrome_counts(self, monkeypatch):
        """`open_browser` pins a real desktop Chrome when one is present, so a
        machine with Chrome and no patchright download is not broken."""
        monkeypatch.setattr(browser_module, "_patchright_chromium_path", lambda: None,
                            raising=False)
        monkeypatch.setattr(browser_module, "find_system_chrome",
                            lambda: "/usr/bin/google-chrome", raising=False)

        assert browser_module.installed_browser_path() == "/usr/bin/google-chrome"

    def test_a_broken_driver_is_not_an_exception(self, monkeypatch):
        """doctor must survive a patchright too broken to answer — this is the
        command you run when things are already wrong."""
        def explode():
            raise RuntimeError("driver did not start")

        monkeypatch.setattr(browser_module, "_patchright_chromium_path", explode,
                            raising=False)
        monkeypatch.setattr(browser_module, "find_system_chrome", lambda: None,
                            raising=False)

        assert browser_module.installed_browser_path() is None
