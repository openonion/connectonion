"""Tests for BrowserAutomation launch configuration."""

import connectonion.useful_tools.browser_tools.browser as browser_mod


class FakePage:
    def set_default_navigation_timeout(self, timeout):
        self.navigation_timeout = timeout

    def set_viewport_size(self, size):
        self.viewport_size = size

    def add_init_script(self, script):
        self.init_script = script


class FakeContext:
    def __init__(self):
        self.page = FakePage()

    def new_page(self):
        return self.page


def test_open_browser_uses_explicit_playwright_channel(monkeypatch, tmp_path):
    captured = {}

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, **kwargs):
            captured["user_data_dir"] = user_data_dir
            captured["kwargs"] = kwargs
            return FakeContext()

    class FakeSyncPlaywright:
        def start(self):
            return type("FakePlaywright", (), {"chromium": FakeChromium()})()

    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", True)
    monkeypatch.setattr(browser_mod, "sync_playwright", lambda: FakeSyncPlaywright())
    monkeypatch.setattr(browser_mod.Path, "home", lambda: tmp_path)

    browser = browser_mod.BrowserAutomation(headless=True, browser_channel="chrome")

    result = browser.open_browser()

    assert "Browser opened with persistent profile" in result
    assert captured["kwargs"]["headless"] is True
    assert captured["kwargs"]["channel"] == "chrome"
    assert "executable_path" not in captured["kwargs"]


def test_browser_install_hint_matches_explicit_channel(monkeypatch):
    monkeypatch.setattr(browser_mod, "PLAYWRIGHT_AVAILABLE", False)
    browser = browser_mod.BrowserAutomation(browser_channel="chrome")

    assert "playwright install chrome" in browser.open_browser()
