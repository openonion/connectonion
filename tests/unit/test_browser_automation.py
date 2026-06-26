"""Tests for BrowserAutomation lifecycle behavior."""

import json

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


class _RecordingContext(FakeContext):
    """A context that records add_cookies / storage_state so seeding/export can be asserted."""

    def __init__(self):
        super().__init__()
        self.added_cookies = None
        self.saved_state_path = None

    def add_cookies(self, cookies):
        self.added_cookies = cookies

    def storage_state(self, path=None):
        self.saved_state_path = path


def _recording_playwright(contexts):
    """sync_playwright() stand-in whose contexts record add_cookies / storage_state calls."""

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            context = _RecordingContext()
            contexts.append(context)
            return context

    class FakePlaywright:
        def __init__(self):
            self.chromium = FakeChromium()

        def stop(self):
            pass

    class FakeSyncPlaywright:
        def start(self):
            return FakePlaywright()

    return FakeSyncPlaywright()


def test_seed_state_injects_exported_cookies(monkeypatch, tmp_path):
    cookies = [{"name": "li_at", "value": "secret", "domain": ".linkedin.com", "path": "/"}]
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"cookies": cookies}))

    contexts = []
    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: _recording_playwright(contexts))
    monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)

    browser = browser_mod.BrowserAutomation(headless=True, seed_state=str(state))
    browser.open_browser()

    assert contexts[0].added_cookies == cookies


def test_no_seed_state_injects_nothing(monkeypatch, tmp_path):
    contexts = []
    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: _recording_playwright(contexts))
    monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)

    browser = browser_mod.BrowserAutomation(headless=True)
    browser.open_browser()

    assert contexts[0].added_cookies is None


def test_save_state_exports_storage_state_to_path(monkeypatch, tmp_path):
    contexts = []
    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: _recording_playwright(contexts))
    monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)

    browser = browser_mod.BrowserAutomation(headless=True)
    browser.open_browser()
    out = tmp_path / "exported.json"
    result = browser.save_state(str(out))

    assert contexts[0].saved_state_path == str(out)
    assert "Saved login state" in result


def test_save_state_without_browser_reports_not_open():
    browser = browser_mod.BrowserAutomation(headless=True)

    assert browser.save_state("/tmp/whatever.json") == "Browser not open"


def test_wait_for_manual_login_refuses_without_tty(monkeypatch):
    """On a host (no interactive stdin) manual login must return immediately rather than
    block input() on the single shared browser worker thread — that thread serializes
    every session's browser ops, so blocking it would freeze them all indefinitely."""
    class _NoTTY:
        def isatty(self):
            return False

    monkeypatch.setattr(browser_mod.sys, "stdin", _NoTTY())

    browser = browser_mod.BrowserAutomation(headless=True)
    browser.browser = FakeContext()
    try:
        result = browser.wait_for_manual_login("Example")
    finally:
        browser._executor.shutdown(wait=False)

    assert "interactive terminal" in result
    assert "seed_state" in result
