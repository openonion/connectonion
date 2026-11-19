"""A headed browser cannot start on a machine with no display, and nothing checked.

`co browser` defaults to headless=False — right on a laptop, impossible on a
deployed agent. Measured on a real Linux server (no DISPLAY set, chromium
installed):

    p.chromium.launch(headless=False)
    → BrowserType.launch: Target page, context or browser has been closed
    p.chromium.launch(headless=True)
    → OK

The message names nothing a reader could act on. And the whole documented
remote-browser story goes through this — .co/host.yaml calls
`RemoteAgent.call("bash", command="co browser take_screenshot")` THE remote
browser entry point — so on every `co deploy`ed agent it fails twice: no browser
installed (fixed in the previous commit), then no display.

The check belongs where headless becomes effective — BrowserAutomation.__init__
— not in the CLI: the daemon, the agent tools, and a plain library caller all
arrive by different routes, and this release has repeatedly been bitten by a
decision made in some of the places that reach it. One place, every route.

grep for DISPLAY in connectonion/ before this commit found exactly one hit, in
the co-ai Dockerfile (`ENV DISPLAY=:99`) — which is also why the second half
matters: a DISPLAY that is set but has no X server behind it still fails headed,
and that failure now says what happened instead of returning only a log path.
"""

import platform

import pytest

from connectonion.useful_tools.browser_tools import browser as browser_module


class TestHeadlessIsForcedWhenThereIsNoDisplay:

    @pytest.fixture(autouse=True)
    def on_linux(self, monkeypatch):
        monkeypatch.setattr(browser_module.platform, "system", lambda: "Linux")

    def test_no_display_means_headless(self, monkeypatch):
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        assert browser_module.headless_without_a_display(False) is True

    def test_a_display_leaves_the_choice_alone(self, monkeypatch):
        monkeypatch.setenv("DISPLAY", ":0")

        assert browser_module.headless_without_a_display(False) is False

    def test_wayland_counts_as_a_display(self, monkeypatch):
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")

        assert browser_module.headless_without_a_display(False) is False

    def test_an_empty_display_is_not_a_display(self, monkeypatch):
        """`DISPLAY=` exports an empty string — the shape a stripped environment
        takes, and what the real server showed: DISPLAY=[]."""
        monkeypatch.setenv("DISPLAY", "")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        assert browser_module.headless_without_a_display(False) is True

    def test_headless_true_stays_true(self, monkeypatch):
        monkeypatch.setenv("DISPLAY", ":0")

        assert browser_module.headless_without_a_display(True) is True


def _windows_session(monkeypatch, number):
    import ctypes
    import types

    def session_id(pid, out):
        out._obj.value = number
        return 1

    kernel32 = types.SimpleNamespace(ProcessIdToSessionId=session_id)
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(kernel32=kernel32), raising=False)
    monkeypatch.setattr(browser_module.platform, "system", lambda: "Windows")


class TestADesktopIsNeverForcedHeadless:
    """macOS always has a display, and so does a Windows desktop session;
    DISPLAY is a thing they lack."""

    def test_macos_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(browser_module.platform, "system", lambda: "Darwin")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        assert browser_module.headless_without_a_display(False) is False

    def test_a_windows_desktop_session_is_left_alone(self, monkeypatch):
        _windows_session(monkeypatch, 1)

        assert browser_module.headless_without_a_display(False) is False


def test_windows_session_zero_runs_headless(monkeypatch):
    # Services, OpenSSH logins and scheduled tasks run in session 0, where no
    # window can ever show: a headed go_to waited 120 s on a 1Cyber PC (#3168).
    _windows_session(monkeypatch, 0)

    assert browser_module.headless_without_a_display(False) is True


class TestTheBrowserItselfHonoursIt:
    """Not the helper in isolation — what a caller asking for headed actually gets."""

    def test_a_headed_request_on_a_display_less_server_becomes_headless(self, monkeypatch):
        monkeypatch.setattr(browser_module.platform, "system", lambda: "Linux")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        automation = browser_module.BrowserAutomation(headless=False)
        try:
            assert automation._headless is True
        finally:
            automation.close()

    @pytest.mark.skipif(platform.system() != "Darwin", reason="desktop-only claim")
    def test_a_desktop_still_gets_a_window(self):
        automation = browser_module.BrowserAutomation(headless=False)
        try:
            assert automation._headless is False
        finally:
            automation.close()


# The advice for a launch failure is not tested here. It moved to
# test_browser_launch_advice.py::TestTheDisplayAdviceOnlyFiresWhenItApplies,
# which already owned "the advice must match the failure" and now covers the
# cases this file's first version got wrong: it asserted the Linux display
# advice with DISPLAY unset, which is the normal case (BrowserAutomation runs
# headless then, so a headed launch never happens) and made the message
# contradict itself — "DISPLAY='' is set". One rule, one place.
