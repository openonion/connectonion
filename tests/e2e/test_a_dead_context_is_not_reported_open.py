"""The daemon calls a gone browser open and fails every command (#711).

Reproduced against the running daemon while preparing 1.6.0 — every command,
not just one, and it does not recover on its own:

    $ co browser go_to https://chat.openonion.ai
    TargetClosedError: BrowserContext.new_page: Target page, context or browser
    has been closed
    $ co browser go_to https://chat.openonion.ai      # again
    TargetClosedError: BrowserContext.new_page: ...

`_context_is_alive` decides this, and it asks the wrong question:

    # Alive = the context still answers protocol calls. Zero open pages is
    # still alive (a page opens on demand), so listing pages IS the check.
    try:
        list(self.browser.pages)
    except Exception:
        return False
    return True

`pages` is a local list, not a protocol call. Measured on a real persistent
context, closed:

    list(ctx.pages)  ->  0 pages, no exception     the liveness check passes
    ctx.new_page()   ->  TargetClosedError         what every command hits
    ctx.cookies()    ->  TargetClosedError
    ctx.is_closed()  ->  True

So the serve loop never exits, `co browser status` reports "open"
(daemon.py:351 uses the same check), and the endpoint stays bound by a daemon
that cannot do anything. Nothing in the process can recover: `open_browser` has
a teardown-and-relaunch path, but per-command dispatch goes through
`_ensure_page`, which guards `if not self.browser` and whether the *page* is
closed — never whether the context is.

The check is `is_closed()`, with the cookies() round-trip behind it for a driver
that does not have it. `pages` stays as a last resort so a stubbed context in
some other test does not start reporting dead.

## Why this test opens a real browser

The first attempt at #711 checked `context.browser`, which is None for
launch_persistent_context — the check was inert and the unit tests passed only
because a MagicMock had the attribute the real object does not. So the context
here is a real one from the real driver, and it is closed the way the field
closes it.
"""

import pytest

from connectonion.useful_tools.browser_tools.browser import BrowserAutomation


try:
    from patchright.sync_api import sync_playwright

    DRIVER = True
except ImportError:  # pragma: no cover
    DRIVER = False


@pytest.fixture
def real_context():
    """A live persistent context from the real driver, and a way to close it."""
    if not DRIVER:
        pytest.skip("patchright not installed")

    import tempfile

    from connectonion.useful_tools.browser_tools.browser_config import (
        CHROME_DEFAULT_ARGS,
        IGNORE_DEFAULT_ARGS,
    )
    from connectonion.useful_tools.browser_tools.chrome_finder import (
        find_system_chrome,
    )

    driver = sync_playwright().start()
    context = driver.chromium.launch_persistent_context(
        tempfile.mkdtemp(),
        headless=True,
        executable_path=find_system_chrome(),
        args=CHROME_DEFAULT_ARGS,
        ignore_default_args=IGNORE_DEFAULT_ARGS,
        timeout=120000,
    )
    yield context
    try:
        context.close()
    except Exception:
        pass
    driver.stop()


@pytest.mark.slow
class TestTheCheckFollowsTheRealContext:

    def _automation(self, context):
        browser = BrowserAutomation.__new__(BrowserAutomation)
        browser.browser = context
        import threading

        browser._executor_thread = threading.current_thread()
        return browser

    def test_a_live_context_reads_alive(self, real_context):
        assert self._automation(real_context)._context_is_alive() is True

    def test_a_closed_context_reads_dead(self, real_context):
        automation = self._automation(real_context)
        real_context.close()

        assert automation._context_is_alive() is False

    def test_the_old_check_would_have_passed(self, real_context):
        """Kept so the reason this was missed stays visible."""
        real_context.close()

        assert list(real_context.pages) == []

    def test_new_page_really_does_fail_on_it(self, real_context):
        """The failure the user sees, so the fixture is not lying about state."""
        real_context.close()

        with pytest.raises(Exception, match="closed"):
            real_context.new_page()


@pytest.mark.slow
class TestTheBrowserProcessDying:
    """The field case: nobody called close(), the process is simply gone.

    This is what both earlier attempts missed. Everything local still reports
    healthy after a SIGKILL — measured:

        is_closed()      ->  False   (a flag set by close(), and close() never ran)
        len(ctx.pages)   ->  1       (the local list still holds the dead tab)
        ctx.cookies()    ->  TargetClosedError
        ctx.new_page()   ->  TargetClosedError

    So `pages` was replaced with `is_closed()`, which reads correctly on a
    context that was closed politely and identically wrongly on one whose
    browser was killed. Only the round-trip distinguishes them.
    """

    @pytest.fixture
    def killed_context(self):
        if not DRIVER:
            pytest.skip("patchright not installed")

        import os
        import signal
        import subprocess
        import tempfile
        import time

        from connectonion.useful_tools.browser_tools.browser_config import (
            CHROME_DEFAULT_ARGS,
            IGNORE_DEFAULT_ARGS,
        )
        from connectonion.useful_tools.browser_tools.chrome_finder import (
            find_system_chrome,
        )

        profile = tempfile.mkdtemp()
        driver = sync_playwright().start()
        context = driver.chromium.launch_persistent_context(
            profile,
            headless=True,
            executable_path=find_system_chrome(),
            args=CHROME_DEFAULT_ARGS,
            ignore_default_args=IGNORE_DEFAULT_ARGS,
            timeout=120000,
        )
        # Kill only the browser owning this throwaway profile.
        pids = subprocess.run(
            ["pgrep", "-f", f"user-data-dir={profile}"],
            capture_output=True, text=True,
        ).stdout.split()
        if not pids:
            pytest.skip("could not identify the browser process for this profile")
        os.kill(int(pids[0]), signal.SIGKILL)
        time.sleep(3)

        yield context
        driver.stop()

    def _automation(self, context):
        import threading

        browser = BrowserAutomation.__new__(BrowserAutomation)
        browser.browser = context
        browser._executor_thread = threading.current_thread()
        return browser

    def test_it_reads_dead(self, killed_context):
        assert self._automation(killed_context)._context_is_alive() is False

    def test_is_closed_alone_would_have_said_alive(self, killed_context):
        """Kept so the second wrong fix stays on the record."""
        assert killed_context.is_closed() is False

    def test_pages_alone_would_have_said_alive(self, killed_context):
        assert len(list(killed_context.pages)) > 0

    def test_a_command_really_does_fail_on_it(self, killed_context):
        with pytest.raises(Exception, match="closed"):
            killed_context.new_page()


class TestNoContextAtAll:

    def test_none_is_not_alive(self):
        browser = BrowserAutomation.__new__(BrowserAutomation)
        browser.browser = None

        assert browser._context_is_alive() is False


class TestAContextWithoutIsClosed:
    """A driver that predates is_closed() must still be judged, not assumed."""

    class _NoIsClosed:
        def __init__(self, raises):
            self._raises = raises
            self.pages = []

        def cookies(self):
            if self._raises:
                raise RuntimeError("Target page, context or browser has been closed")
            return []

    def _automation(self, context):
        import threading

        browser = BrowserAutomation.__new__(BrowserAutomation)
        browser.browser = context
        browser._executor_thread = threading.current_thread()
        return browser

    def test_a_working_one_reads_alive(self):
        assert self._automation(self._NoIsClosed(raises=False))._context_is_alive() is True

    def test_one_that_refuses_a_round_trip_reads_dead(self):
        assert self._automation(self._NoIsClosed(raises=True))._context_is_alive() is False
