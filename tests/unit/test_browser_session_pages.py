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
import connectonion.useful_tools.browser_tools.browser as browser_mod


@pytest.fixture(autouse=True)
def _reset_browser_session_binding():
    """The browser session key lives in a module-level threading.local; reset it around every
    test so one test's bound session can't leak into the next (open_browser/close branch on it)."""
    browser_mod._session_binding.key = None
    yield
    browser_mod._session_binding.key = None


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

    def test_close_tab_bounds_url_memory(self, browser):
        """_page_url must stay bounded: session ids are unique per panel, so an
        unbounded restore map leaks one url per session forever on a shared host."""
        browser._max_url_memory = 5
        for i in range(20):
            key = f"s{i}"
            page = FakePage(i)
            page.url = f"https://example.com/{i}"
            browser._pages[key] = page
            browser._page_used[key] = time.monotonic()
            browser._close_tab(key)
        assert len(browser._page_url) == 5
        assert "s19" in browser._page_url        # most recently closed kept
        assert "s0" not in browser._page_url     # oldest evicted


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


class TestOpenBrowserSharedContext:
    """A shared BrowserAutomation must not let one session's open_browser/close tear down the
    context other sessions are using. Full teardown is only for an unbound (CLI) caller."""

    @staticmethod
    def _install_mock_playwright(monkeypatch, tmp_path):
        """Patch sync_playwright with a fake; return the list of launched contexts so a test
        can assert how many times the shared context was (re)launched."""
        import connectonion.useful_tools.browser_tools.browser as browser_mod
        launched = []

        class _RecordingContext:
            def __init__(self):
                self.closed = False
                self.n = 0

            def new_page(self):
                self.n += 1
                return FakePage(self.n)

            def add_cookies(self, cookies):
                pass

            def close(self):
                self.closed = True

        class _Chromium:
            def launch_persistent_context(self, *a, **k):
                launched.append(_RecordingContext())
                return launched[-1]

        class _Playwright:
            def __init__(self):
                self.chromium = _Chromium()

            def stop(self):
                pass

        monkeypatch.setattr(browser_mod, "BROWSER_AVAILABLE", True)
        monkeypatch.setattr(browser_mod, "sync_playwright",
                            lambda: type("S", (), {"start": lambda self: _Playwright()})())
        monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)
        return launched

    def test_second_session_open_browser_reuses_context(self, monkeypatch, tmp_path):
        """A second session calling open_browser must REUSE the live shared context, not
        tear it down — otherwise the first session's tabs vanish mid-task."""
        launched = self._install_mock_playwright(monkeypatch, tmp_path)
        b = BrowserAutomation()
        try:
            b._bind_session("A"); b.open_browser()  # session A launches the context + its tab
            b._bind_session("B"); b.open_browser()  # session B must reuse it, not relaunch

            assert len(launched) == 1              # launched once, never relaunched
            assert launched[0].closed is False     # and never torn down
            assert {"A", "B"} <= set(b._pages)     # both sessions have their own tab in it
        finally:
            b._executor.shutdown(wait=False)

    def test_force_from_bound_session_recycles_only_its_tab(self, monkeypatch, tmp_path):
        """open_browser(force=True) from a bound session must recycle only THAT session's tab,
        not tear down the shared context (which would kill every other session)."""
        launched = self._install_mock_playwright(monkeypatch, tmp_path)
        b = BrowserAutomation()
        try:
            b._bind_session("A"); b.open_browser()
            page_a = b._pages["A"]
            b._bind_session("B"); b.open_browser()
            b.open_browser(force=True)             # B forces a fresh start for itself

            assert len(launched) == 1              # shared context never relaunched
            assert launched[0].closed is False
            assert b._pages["A"] is page_a         # A's tab untouched
            assert page_a.closed is False
            assert "B" in b._pages                 # B has a (fresh) tab
        finally:
            b._executor.shutdown(wait=False)

    def test_close_from_bound_session_closes_only_its_tab(self, browser):
        """close() from a bound session closes only that session's tab — the shared context and
        every other session's tab stay intact (full teardown is for an unbound caller)."""
        browser._bind_session("A"); browser._ensure_page("A")
        browser._bind_session("B"); browser._ensure_page("B")
        page_a = browser._pages["A"]
        context = browser.browser

        browser._bind_session("B")
        result = browser.close()

        assert "B" not in browser._pages           # B's own tab closed
        assert browser._pages["A"] is page_a       # A's tab untouched
        assert page_a.closed is False
        assert browser.browser is context          # shared context NOT torn down
        assert "tab" in result.lower()
