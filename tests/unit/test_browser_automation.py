"""Tests for BrowserAutomation lifecycle behavior."""

import connectonion.useful_tools.browser_tools.browser as browser_mod


class FakePage:
    def __init__(self):
        self.closed = False

    def set_default_navigation_timeout(self, timeout):
        self.navigation_timeout = timeout

    def set_viewport_size(self, size):
        self.viewport_size = size

    def add_init_script(self, script):
        self.init_script = script

    def wait_for_timeout(self, timeout):
        self.wait_timeout = timeout

    def close(self):
        self.closed = True


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
    assert second_result == "Browser already open"
    assert len(contexts) == 1
    assert first_page.closed is False
    assert first_context.closed is False
    assert first_playwright.stopped is False
    assert browser.browser is contexts[0]
    assert browser.page is contexts[0].page
