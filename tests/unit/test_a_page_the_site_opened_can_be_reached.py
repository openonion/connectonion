"""A tab the site opened is a tab you must be able to reach.

Reported 2026-09-14: a command opens a page, that page opens a third page in a
new browser tab, and there is no way to work in it. `tab ls` lists the sessions
*we* registered, so a page the site opened appears nowhere, and `use`/`switch`
were removed in 1.8 with "no server-side cursor, targeting is per-command".

That removal was right and is not what this restores. A session is still
targeted per command with `-t`; what was missing is any way to see the browser's
real pages, or to point a session at one of them.

Without it, `target=_blank` is a dead end: the work happens in a tab the agent
cannot name.
"""

import asyncio

import pytest

from connectonion.useful_tools.browser_tools._async_browser import AsyncBrowserCore


class _FakePage:
    def __init__(self, url, title="", closed=False):
        self._url = url
        self._title = title
        self._closed = closed

    @property
    def url(self):
        return self._url

    async def title(self):
        return self._title

    def is_closed(self):
        return self._closed

    def set_default_navigation_timeout(self, _ms):
        pass

    async def set_viewport_size(self, _size):
        pass


class _FakeContext:
    """Stands in for the Playwright BrowserContext and its live page list."""

    def __init__(self, pages):
        self.pages = list(pages)

    async def new_page(self):
        page = _FakePage("about:blank")
        self.pages.append(page)
        return page


def _core(pages):
    core = AsyncBrowserCore(headless=True)
    core.browser = _FakeContext(pages)
    return core


def test_a_page_the_site_opened_is_listed():
    """The one the report is about: nothing we registered, so nothing showed it."""
    mine = _FakePage("https://example.com/start", "Start")
    theirs = _FakePage("https://example.com/popup", "Invoice PDF")
    core = _core([mine, theirs])
    core._pages[None] = mine

    listing = asyncio.run(core.list_pages())

    assert "https://example.com/popup" in listing
    assert "Invoice PDF" in listing
    assert "https://example.com/start" in listing


def test_the_listing_says_which_pages_nobody_is_driving():
    mine = _FakePage("https://example.com/start", "Start")
    theirs = _FakePage("https://example.com/popup", "Popup")
    core = _core([mine, theirs])
    core._pages[None] = mine

    listing = asyncio.run(core.list_pages())

    start = next(line for line in listing.splitlines() if "/start" in line)
    popup = next(line for line in listing.splitlines() if "/popup" in line)
    assert "main" in start, "a driven page names the session driving it"
    assert "unclaimed" in popup


def test_switching_lets_the_session_work_in_that_page():
    mine = _FakePage("https://example.com/start")
    theirs = _FakePage("https://example.com/popup")
    core = _core([mine, theirs])
    core._pages[None] = mine

    asyncio.run(core.switch_page(1))

    assert core._pages[None] is theirs
    assert core.page is theirs, "the next verb must run in the page we switched to"


def test_switching_back_is_just_switching():
    mine = _FakePage("https://example.com/start")
    theirs = _FakePage("https://example.com/popup")
    core = _core([mine, theirs])
    core._pages[None] = mine

    asyncio.run(core.switch_page(1))
    asyncio.run(core.switch_page(0))

    assert core.page is mine


def test_an_index_that_does_not_exist_says_what_does():
    core = _core([_FakePage("https://example.com/only")])

    answer = asyncio.run(core.switch_page(7))

    assert "7" in answer
    assert "https://example.com/only" in answer, "show the pages that do exist"


def test_a_page_another_session_is_driving_is_refused():
    """Same rule as tabs: two agents must not silently share one page."""
    mine = _FakePage("https://example.com/mine")
    theirs = _FakePage("https://example.com/theirs")
    core = _core([mine, theirs])
    core._pages[None] = mine
    core._pages["other"] = theirs

    answer = asyncio.run(core.switch_page(1))

    assert "other" in answer, "name who has it"
    assert core._pages[None] is mine, "and do not take it"


def test_a_closed_page_is_not_offered():
    core = _core(
        [_FakePage("https://example.com/live"), _FakePage("https://example.com/gone", closed=True)]
    )

    listing = asyncio.run(core.list_pages())

    assert "/live" in listing
    assert "/gone" not in listing


def test_it_says_so_when_there_is_no_browser():
    core = AsyncBrowserCore(headless=True)

    assert "not open" in asyncio.run(core.list_pages()).lower()
    assert "not open" in asyncio.run(core.switch_page(0)).lower()


def test_the_tab_board_points_at_the_listing_when_a_page_is_unclaimed():
    """Discoverability: nobody reads help for a verb they do not know exists."""
    mine = _FakePage("https://example.com/start")
    theirs = _FakePage("https://example.com/popup")
    core = _core([mine, theirs])
    core._pages[None] = mine
    core._tab_meta[None] = {"who": "agent", "purpose": "work"}

    board = asyncio.run(core.tab_status())

    assert "list_pages" in board
