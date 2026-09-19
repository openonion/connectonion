"""`wait` takes seconds, and a millisecond-shaped argument says so immediately.

#1509: three unattended LinkedIn rounds died because `wait 2500` was read as
milliseconds by the caller and as seconds by the verb.  Forty-one minutes of
`page.wait_for_timeout` held the tab's operation lock, so every later command on
that tab queued behind it and hit the client's 120s ceiling.  From outside it
looked like a wedged daemon: `status` answered, other tabs worked, and a health
probe found nothing to restart.

The damage is not that the number was wrong.  It is that a wrong number bought a
silent forty-one minute hold on a shared resource.  A cap turns it into one line
of text before anything is acquired.
"""

import asyncio
import json

import pytest

from connectonion.cli.browser_agent.daemon import BrowserDaemon
from connectonion.useful_tools.browser_tools._async_browser import (
    MAX_WAIT_SECONDS,
    AsyncBrowserCore,
)
from connectonion.useful_tools.browser_tools.browser import LegacyBrowserAutomation


def envelope(line: str, *, caller: str, tab: str | None = None) -> str:
    return json.dumps(
        {"v": 1, "caller": caller, "account": "", "tab": tab, "line": line}
    )


@pytest.fixture
def daemon(tmp_path):
    server = BrowserDaemon(str(tmp_path / "browser.sock"), headless=True)
    server.browser = AsyncBrowserCore(headless=True)
    return server


class _CountingPage:
    """Stands in for the Playwright page so a passing wait can be observed."""

    def __init__(self):
        self.slept_ms = []

    async def wait_for_timeout(self, ms):
        self.slept_ms.append(ms)


def _core_with_page():
    """A core whose bound tab has a page, without starting a real browser."""
    core = AsyncBrowserCore(headless=True)
    page = _CountingPage()
    core._pages[core._bound_session_key()] = page
    return core, page


def test_a_millisecond_argument_is_refused_by_the_async_core():
    core, page = _core_with_page()

    with pytest.raises(ValueError) as caught:
        asyncio.run(core.wait(2500))

    message = str(caught.value)
    assert "seconds" in message
    assert "2.5" in message, "it must name the value the caller almost certainly meant"
    assert page.slept_ms == [], "nothing may be slept on before the refusal"


def test_the_refusal_happens_before_the_browser_is_even_consulted():
    """A unit mistake is a unit mistake with or without a page open."""
    core = AsyncBrowserCore(headless=True)

    with pytest.raises(ValueError):
        asyncio.run(core.wait(2500))


def test_an_ordinary_wait_still_waits():
    core, page = _core_with_page()

    assert asyncio.run(core.wait(2.5)) == "Waited for 2.5 seconds"
    assert page.slept_ms == [2500]


def test_the_cap_itself_is_allowed_and_one_second_past_it_is_not():
    core, page = _core_with_page()

    asyncio.run(core.wait(MAX_WAIT_SECONDS))
    assert page.slept_ms == [MAX_WAIT_SECONDS * 1000]

    with pytest.raises(ValueError):
        asyncio.run(core.wait(MAX_WAIT_SECONDS + 1))


def test_the_legacy_sync_implementation_refuses_the_same_argument():
    """The public facade delegates to the async core, so it is covered above.

    The pre-asyncio implementation is still shipped as the comparison oracle for
    the verb contract, and a limit the two disagree about is not a limit.  Called
    unbound on purpose, past the browser-thread decorator: the guard must fire
    before `self.page` is read, so it needs nothing from a started browser.
    """

    class _NothingStarted:
        pass

    with pytest.raises(ValueError) as caught:
        LegacyBrowserAutomation.wait.__wrapped__(_NothingStarted(), 2500)

    assert "seconds" in str(caught.value)


@pytest.mark.asyncio
async def test_the_tab_is_free_the_moment_the_bad_wait_is_refused(daemon):
    """The point of the fix: the mistake costs a round trip, not the tab."""
    ok, payload = await daemon.dispatch_async(
        envelope("tab open probe --who agent --for testing", caller="agent")
    )
    assert ok is True, payload

    ok, payload = await daemon.dispatch_async(
        envelope("wait 2500", caller="agent", tab="probe")
    )
    assert ok is not True, "a 41-minute sleep must not be accepted"
    assert "seconds" in payload

    # If the wait had been admitted, this would queue behind it for 41 minutes.
    ok, payload = await asyncio.wait_for(
        daemon.dispatch_async(envelope("status", caller="agent", tab="probe")),
        timeout=10,
    )
    assert ok is True, payload
