"""Tests for BrowserAutomation lifecycle behavior."""

import connectonion.useful_tools.browser_tools.browser as browser_mod


class FakePage:
    def __init__(self):
        self.closed = False
        self.url = "about:blank"

    def set_default_navigation_timeout(self, timeout):
        self.navigation_timeout = timeout

    def set_viewport_size(self, size):
        self.viewport_size = size

    def add_init_script(self, script):
        self.init_script = script

    def wait_for_timeout(self, timeout):
        if self.closed:
            raise RuntimeError("page is closed")
        self.wait_timeout = timeout

    def close(self):
        if self.closed:
            raise RuntimeError("page is closed")
        self.closed = True

    def is_closed(self):
        return self.closed


class FakeContext:
    def __init__(self):
        self.page = FakePage()
        self.closed = False

    def new_page(self):
        return self.page

    def close(self):
        self.closed = True


def test_open_browser_is_noop_when_context_is_already_open(monkeypatch, tmp_path):
    contexts = []
    playwrights = []

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            context = FakeContext()
            contexts.append(context)
            return context

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()
            self.stopped = False

        def stop(self):
            self.stopped = True

    class FakeSyncPlaywright:
        def start(self):
            playwright = FakePlaywright()
            playwrights.append(playwright)
            return playwright

    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: FakeSyncPlaywright())
    monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)

    browser = browser_mod.BrowserAutomation(headless=True)

    first_result = browser.open_browser()
    first_context = contexts[0]
    first_page = first_context.page
    first_playwright = playwrights[0]

    second_result = browser.open_browser()

    assert "Browser opened with persistent profile" in first_result
    assert second_result == "<system-reminder>Browser already open and usable. Continue using the current browser page.</system-reminder>"
    assert len(contexts) == 1
    assert first_page.closed is False
    assert first_context.closed is False
    assert first_playwright.stopped is False
    assert browser.browser is contexts[0]
    assert browser.page is contexts[0].page


def test_open_browser_force_reopens_existing_context(monkeypatch, tmp_path):
    contexts = []
    playwrights = []

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            context = FakeContext()
            contexts.append(context)
            return context

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()
            self.stopped = False

        def stop(self):
            self.stopped = True

    class FakeSyncPlaywright:
        def start(self):
            playwright = FakePlaywright()
            playwrights.append(playwright)
            return playwright

    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: FakeSyncPlaywright())
    monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)

    browser = browser_mod.BrowserAutomation(headless=True)
    browser.open_browser()
    first_context = contexts[0]
    first_page = first_context.page
    first_playwright = playwrights[0]

    result = browser.open_browser(force=True)

    assert "Previous browser closed by force" in result
    assert len(contexts) == 2
    assert first_page.closed is True
    assert first_context.closed is True
    assert first_playwright.stopped is True
    assert browser.browser is contexts[1]
    assert browser.page is contexts[1].page


def test_open_browser_reopens_stale_context(monkeypatch, tmp_path):
    contexts = []
    playwrights = []

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            context = FakeContext()
            contexts.append(context)
            return context

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()
            self.stopped = False

        def stop(self):
            self.stopped = True

    class FakeSyncPlaywright:
        def start(self):
            playwright = FakePlaywright()
            playwrights.append(playwright)
            return playwright

    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: FakeSyncPlaywright())
    monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)

    browser = browser_mod.BrowserAutomation(headless=True)
    browser.open_browser()
    first_context = contexts[0]
    first_page = first_context.page
    first_playwright = playwrights[0]
    first_page.close()

    result = browser.open_browser()

    assert "Previous stale browser state closed" in result
    assert len(contexts) == 2
    assert first_context.closed is True
    assert first_playwright.stopped is True
    assert browser.browser is contexts[1]
    assert browser.page is contexts[1].page


def test_close_reports_cleanup_warnings_and_clears_state():
    browser = browser_mod.BrowserAutomation(headless=True)
    page = FakePage()
    page.close()
    context = FakeContext()
    playwright = type("FakePlaywright", (), {"stop": lambda self: None})()
    browser.page = page
    browser.browser = context
    browser.playwright = playwright

    result = browser.close()

    assert "Browser closed with cleanup warnings" in result
    assert "save context failed" in result
    assert "close page failed" in result
    assert browser.page is None
    assert browser.browser is None
    assert browser.playwright is None
