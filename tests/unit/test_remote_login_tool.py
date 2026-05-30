"""Tests for the packaged remote_login tool lifecycle."""

import importlib
from types import SimpleNamespace

remote_login_mod = importlib.import_module("connectonion.useful_tools.remote_login")


class FakePage:
    url = "https://example.com/login"

    def __init__(self):
        self.goto_calls = []
        self.waits = []

    def goto(self, url, wait_until=None, timeout=None):
        self.url = url
        self.goto_calls.append((url, wait_until, timeout))

    def wait_for_timeout(self, timeout):
        self.waits.append(timeout)


class FakeBrowser:
    def __init__(self):
        self.page = FakePage()
        self.closed = False

    def close(self):
        self.closed = True


def test_remote_login_uses_per_call_browser_and_closes(monkeypatch):
    opened = []

    def fake_open_browser(headless):
        browser = FakeBrowser()
        opened.append((headless, browser))
        return browser

    monkeypatch.setattr(remote_login_mod, "_open_browser", fake_open_browser)
    monkeypatch.setattr(remote_login_mod, "_is_logged_in", lambda browser: True)

    result = remote_login_mod.remote_login(SimpleNamespace(), "https://example.com/login")

    assert result == "已登录 https://example.com/login（复用已存登录态）"
    assert len(opened) == 1
    assert opened[0][0] is False
    assert opened[0][1].page.goto_calls == [("https://example.com/login", "domcontentloaded", 30000)]
    assert opened[0][1].closed is True
