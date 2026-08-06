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
from connectonion.cli.browser_agent.daemon import launch_failure_advice


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


class TestADesktopIsNeverForcedHeadless:
    """macOS and Windows always have a display; DISPLAY is a thing they lack."""

    @pytest.mark.parametrize("system", ["Darwin", "Windows"])
    def test_the_choice_is_left_alone(self, monkeypatch, system):
        monkeypatch.setattr(browser_module.platform, "system", lambda: system)
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

        assert browser_module.headless_without_a_display(False) is False


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
            automation._executor.shutdown(wait=False)

    @pytest.mark.skipif(platform.system() != "Darwin", reason="desktop-only claim")
    def test_a_desktop_still_gets_a_window(self):
        automation = browser_module.BrowserAutomation(headless=False)
        try:
            assert automation._headless is False
        finally:
            automation._executor.shutdown(wait=False)


class TestTheAdviceCoversADeadDisplay:
    """A DISPLAY that is set with no X server behind it — what the co-ai
    Dockerfile's `ENV DISPLAY=:99` produces if Xvfb is not running — still fails
    headed, and the advice for it was an empty string plus a log path."""

    MEASURED = "BrowserType.launch: Target page, context or browser has been closed"

    def test_linux_gets_more_than_a_log_path(self, monkeypatch):
        monkeypatch.setattr("connectonion.cli.browser_agent.daemon.platform.system",
                            lambda: "Linux")

        advice = launch_failure_advice(self.MEASURED)

        assert "--headless" in advice or "headless" in advice.lower()
        assert "DISPLAY" in advice

    def test_it_does_not_hand_a_server_the_macos_advice(self, monkeypatch):
        monkeypatch.setattr("connectonion.cli.browser_agent.daemon.platform.system",
                            lambda: "Linux")

        assert "desktop Terminal" not in launch_failure_advice(self.MEASURED)

    def test_a_missing_executable_still_says_install(self, monkeypatch):
        """The existing branch, which is the more common failure — unchanged."""
        monkeypatch.setattr("connectonion.cli.browser_agent.daemon.platform.system",
                            lambda: "Linux")

        advice = launch_failure_advice("Executable doesn't exist at /home/co/.cache/...")

        assert "patchright install chromium" in advice
