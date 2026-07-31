"""What we tell someone when the browser will not start.

Two different failures wear the same exception, and the advice for one is
nonsense for the other. A deployed agent on a Linux server was told to "run
`co browser` from a desktop Terminal" when what it actually needed was the
browser installed — the executable was simply not there.
"""

from unittest.mock import patch

from connectonion.cli.browser_agent import daemon


class TestTheAdviceMatchesTheFailure:
    def test_a_missing_browser_says_how_to_install_it(self):
        advice = daemon.launch_failure_advice(
            "Executable doesn't exist at /home/co/.cache/ms-playwright/chromium-1228/chrome")

        assert "patchright install chromium" in advice
        assert "desktop Terminal" not in advice, \
            "a server has no desktop, and that is not what is wrong"

    def test_a_missing_browser_says_the_same_on_macos(self):
        """The cause is the same on either platform, so the advice is too."""
        with patch.object(daemon.platform, "system", return_value="Darwin"):
            advice = daemon.launch_failure_advice("Executable doesn't exist at /Users/…")

        assert "patchright install chromium" in advice

    def test_a_headless_session_on_macos_gets_the_session_advice(self):
        with patch.object(daemon.platform, "system", return_value="Darwin"):
            advice = daemon.launch_failure_advice("Target page or browser has been closed")

        assert "desktop Terminal" in advice

    def test_linux_is_not_told_about_macos_window_sessions(self):
        with patch.object(daemon.platform, "system", return_value="Linux"):
            advice = daemon.launch_failure_advice("Target page or browser has been closed")

        assert "desktop Terminal" not in advice
        assert "browser.log" in advice
