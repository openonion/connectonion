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

        assert "onionwright install chromium" in advice
        assert "desktop Terminal" not in advice, \
            "a server has no desktop, and that is not what is wrong"

    def test_a_missing_browser_says_the_same_on_macos(self):
        """The cause is the same on either platform, so the advice is too."""
        with patch.object(daemon.platform, "system", return_value="Darwin"):
            advice = daemon.launch_failure_advice("Executable doesn't exist at /Users/…")

        assert "onionwright install chromium" in advice

    def test_a_headless_session_on_macos_gets_the_session_advice(self):
        with patch.object(daemon.platform, "system", return_value="Darwin"):
            advice = daemon.launch_failure_advice("Target page or browser has been closed")

        assert "desktop Terminal" in advice

    def test_linux_is_not_told_about_macos_window_sessions(self):
        with patch.object(daemon.platform, "system", return_value="Linux"):
            advice = daemon.launch_failure_advice("Target page or browser has been closed")

        assert "desktop Terminal" not in advice
        assert "browser.log" in advice


class TestTheDisplayAdviceOnlyFiresWhenItApplies:
    """The Linux branch was added for a display that is configured but dead —
    `ENV DISPLAY=:99` with no Xvfb behind it. As written it answered EVERY Linux
    failure that was not a missing executable, which is the same mistake this
    whole file exists to prevent: a confident diagnosis of the wrong thing.

    With DISPLAY unset it also contradicted itself, printing "DISPLAY='' is set
    but no display answered" — and DISPLAY unset is the normal case, because
    BrowserAutomation then runs headless and a headed launch never happens.
    """

    CLOSED = "BrowserType.launch: Target page, context or browser has been closed"

    def test_a_dead_display_is_diagnosed(self, monkeypatch):
        monkeypatch.setenv("DISPLAY", ":99")
        with patch.object(daemon.platform, "system", return_value="Linux"):
            advice = daemon.launch_failure_advice(self.CLOSED)

        assert "DISPLAY" in advice
        assert "Xvfb" in advice

    def test_no_display_set_gets_no_display_advice(self, monkeypatch):
        """Nothing to say about a display that was never configured."""
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        with patch.object(daemon.platform, "system", return_value="Linux"):
            advice = daemon.launch_failure_advice(self.CLOSED)

        assert "is set but no display answered" not in advice

    def test_an_unrelated_linux_failure_is_not_blamed_on_the_display(self, monkeypatch):
        """A profile lock, an OOM kill, a crashed Chrome — none of them are the
        display, and saying so sends the reader somewhere there is nothing."""
        monkeypatch.setenv("DISPLAY", ":99")
        with patch.object(daemon.platform, "system", return_value="Linux"):
            advice = daemon.launch_failure_advice(
                "BrowserType.launchPersistentContext: Failed to create a ProcessSingleton"
                " for your profile directory")

        assert "no display answered" not in advice

    def test_it_still_names_the_log_in_every_case(self, monkeypatch):
        monkeypatch.setenv("DISPLAY", ":99")
        with patch.object(daemon.platform, "system", return_value="Linux"):
            for line in (self.CLOSED, "Failed to create a ProcessSingleton"):
                assert "~/.co/browser.log" in daemon.launch_failure_advice(line), line


class TestTheLogIsAlwaysNamed:
    """Whatever else is wrong, the full log is where the rest of it is. A rewrite
    of this message dropped the pointer from two of the three branches, and a
    test that had asserted it since before the rewrite caught it."""

    def test_every_branch_names_the_log(self):
        for system in ("Darwin", "Linux"):
            with patch.object(daemon.platform, "system", return_value=system):
                for line in ("Executable doesn't exist at /x",
                             "Target page or browser has been closed"):
                    assert "~/.co/browser.log" in daemon.launch_failure_advice(line), \
                        (system, line)
