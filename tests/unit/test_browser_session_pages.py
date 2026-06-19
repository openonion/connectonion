"""Unit tests for per-session browser tabs in BrowserAutomation.

Each session (chat panel) gets its own tab in the shared context so concurrent
sessions don't navigate over each other. Tabs are reclaimed by idle-TTL and a
max-tabs backstop, and a reclaimed session transparently gets a fresh tab restored
to its last URL (never a "target closed" crash).

These tests fake the Playwright context/page, so they need no real browser.
"""

import time
import threading

import pytest

from connectonion.useful_tools.browser_tools.browser import BrowserAutomation


class FakePage:
    def __init__(self, idx):
        self.idx = idx
        self.url = f"about:blank#{idx}"
        self.closed = False
        self.goto_calls = []

    def set_default_navigation_timeout(self, *a, **k):
        pass

    def set_viewport_size(self, *a, **k):
        pass

    def add_init_script(self, *a, **k):
        pass

    def goto(self, url, **k):
        self.goto_calls.append(url)
        self.url = url

    def is_closed(self):
        return self.closed

    def close(self):
        self.closed = True


class ThreadCheckingPage(FakePage):
    def __init__(self, idx):
        self.url_thread = None
        self._url = ""
        super().__init__(idx)

    @property
    def url(self):
        self.url_thread = threading.current_thread()
        return self._url

    @url.setter
    def url(self, value):
        self._url = value


class FakeContext:
    def __init__(self):
        self.n = 0

    def new_page(self):
        self.n += 1
        return FakePage(self.n)


@pytest.fixture
def browser():
    b = BrowserAutomation()
    b.browser = FakeContext()        # stand in for the launched persistent context
    b._bind_session(None)            # reset this thread's binding between tests
    yield b
    b._executor.shutdown(wait=False)


class TestPerSessionTabs:
    def test_each_session_gets_its_own_tab(self, browser):
        browser._bind_session("A")
        browser._ensure_page("A")
        page_a = browser.page

        browser._bind_session("B")
        browser._ensure_page("B")
        page_b = browser.page

        assert page_a is not page_b
        assert {"A", "B"} <= set(browser._pages)

    def test_page_property_routes_by_bound_session(self, browser):
        browser._bind_session("A"); browser._ensure_page("A")
        browser._bind_session("B"); browser._ensure_page("B")

        browser._bind_session("A")
        assert browser.page is browser._pages["A"]
        browser._bind_session("B")
        assert browser.page is browser._pages["B"]

    def test_navigating_one_session_does_not_touch_another(self, browser):
        browser._bind_session("A"); browser._ensure_page("A")
        browser._bind_session("B"); browser._ensure_page("B")

        browser._pages["A"].goto("https://linkedin.com")
        # B's tab is a different page object, unaffected by A's navigation.
        assert browser._pages["B"].url != "https://linkedin.com"

    def test_no_session_uses_a_single_shared_tab(self, browser):
        browser._bind_session(None)
        browser._ensure_page(None)
        browser._ensure_page(None)
        assert list(browser._pages) == [None]
        assert browser.page is browser._pages[None]

    def test_browser_is_usable_dispatches_to_browser_thread(self, browser):
        page = ThreadCheckingPage(1)
        browser._pages[None] = page
        browser._page_used[None] = time.monotonic()

        assert threading.current_thread() is not browser._executor_thread
        assert browser._browser_is_usable() is True
        assert page.url_thread is browser._executor_thread


class TestTabReclaim:
    def test_idle_tab_is_reclaimed_and_active_is_kept(self, browser):
        browser._bind_session("A"); browser._ensure_page("A")
        browser._bind_session("B"); browser._ensure_page("B")
        page_a = browser._pages["A"]

        browser._tab_idle_ttl = 3600
        browser._page_used["A"] = time.monotonic() - 10_000  # A abandoned long ago

        browser._bind_session("B")
        browser._ensure_page("B")  # reclaim runs with active=B

        assert "A" not in browser._pages          # idle tab closed
        assert page_a.closed is True
        assert "B" in browser._pages              # active tab kept
        assert browser._page_url["A"]             # url remembered for restore

    def test_reclaimed_session_recreates_and_restores_url(self, browser):
        browser._bind_session("A"); browser._ensure_page("A")
        browser._pages["A"].goto("https://example.com/feed")

        browser._tab_idle_ttl = 0
        browser._bind_session("B")
        browser._ensure_page("B")  # active=B; A idle past ttl=0 -> reclaimed

        assert "A" not in browser._pages

        browser._bind_session("A")
        browser._ensure_page("A")  # A returns -> fresh tab restored to its url
        assert browser._pages["A"].goto_calls == ["https://example.com/feed"]

    def test_max_tabs_backstop_evicts_lru_not_active(self, browser):
        browser._max_tabs = 2
        browser._tab_idle_ttl = 10_000  # disable idle path; test the hard cap only
        for key in ("A", "B", "C"):
            browser._bind_session(key)
            browser._ensure_page(key)

        assert len(browser._pages) == 2
        assert "C" in browser._pages          # the active one is never evicted
        assert "A" not in browser._pages      # least-recently-used evicted

    def test_does_not_evict_when_under_cap_and_not_idle(self, browser):
        browser._max_tabs = 10
        browser._tab_idle_ttl = 10_000
        for key in ("A", "B", "C"):
            browser._bind_session(key)
            browser._ensure_page(key)
        assert set(browser._pages) == {"A", "B", "C"}


class TestBindSessionPlugin:
    def test_handler_binds_current_session_to_browser(self):
        """The plugin reads the turn's session_id and hands it to the browser."""
        from connectonion.useful_plugins.bind_browser_session import _bind_session

        class FakeBrowser:
            bound = "unset"
            def _bind_session(self, sid):
                self.bound = sid

        class FakeAgent:
            class tools:
                browserautomation = FakeBrowser()
            current_session = {"session_id": "sess-123"}

        _bind_session(FakeAgent())
        assert FakeAgent.tools.browserautomation.bound == "sess-123"

    def test_handler_noop_without_browser(self):
        """Agents with no browser tool are unaffected — the plugin does nothing."""
        from connectonion.useful_plugins.bind_browser_session import _bind_session

        class FakeAgent:
            class tools:
                pass
            current_session = {"session_id": "sess-123"}

        _bind_session(FakeAgent())  # must not raise
