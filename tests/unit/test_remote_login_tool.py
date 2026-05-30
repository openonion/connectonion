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


class RaisingLLM:
    def complete(self, *args, **kwargs):
        raise RuntimeError("model unavailable")


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


def test_login_step_uses_agent_qr_verdict_over_script_hint(monkeypatch):
    browser = FakeBrowser()
    filled = []
    sent_shots = []
    scan_prompts = []

    monkeypatch.setattr(remote_login_mod, "_page_has_qr_login", lambda _browser: True)
    monkeypatch.setattr(remote_login_mod, "_page_has_credential_login", lambda _browser: False)
    monkeypatch.setattr(remote_login_mod, "_classify_login_method", lambda _agent, _browser: "credentials")
    monkeypatch.setattr(remote_login_mod, "_send_shot", lambda _agent, _browser: sent_shots.append(True))
    monkeypatch.setattr(remote_login_mod, "ask_user", lambda _agent, question, options: scan_prompts.append((question, options)))
    monkeypatch.setattr(remote_login_mod, "_fill_password", lambda _agent, _browser, question: filled.append(question))

    remote_login_mod._handle_login_step(SimpleNamespace(), browser)

    assert filled == ["请输入账号和密码"]
    assert sent_shots == []
    assert scan_prompts == []


def test_login_step_sends_qr_when_agent_sees_qr_even_without_script_hint(monkeypatch):
    browser = FakeBrowser()
    filled = []
    sent_shots = []
    scan_prompts = []

    monkeypatch.setattr(remote_login_mod, "_page_has_qr_login", lambda _browser: False)
    monkeypatch.setattr(remote_login_mod, "_page_has_credential_login", lambda _browser: True)
    monkeypatch.setattr(remote_login_mod, "_classify_login_method", lambda _agent, _browser: "qr")
    monkeypatch.setattr(remote_login_mod, "_send_shot", lambda _agent, _browser: sent_shots.append(True))
    monkeypatch.setattr(remote_login_mod, "ask_user", lambda _agent, question, options: scan_prompts.append((question, options)))
    monkeypatch.setattr(remote_login_mod, "_fill_password", lambda _agent, _browser, question: filled.append(question))

    remote_login_mod._handle_login_step(SimpleNamespace(), browser)

    assert sent_shots == [True]
    assert scan_prompts == [("请用手机扫描上面的二维码，完成后点这里", ["扫好了"])]
    assert filled == []


def test_login_step_does_not_fallback_to_qr_script_hint_when_agent_fails(monkeypatch):
    browser = FakeBrowser()
    filled = []
    sent_shots = []
    scan_prompts = []

    monkeypatch.setattr(remote_login_mod, "_page_has_qr_login", lambda _browser: True)
    monkeypatch.setattr(remote_login_mod, "_page_has_credential_login", lambda _browser: False)
    monkeypatch.setattr(remote_login_mod, "_send_shot", lambda _agent, _browser: sent_shots.append(True))
    monkeypatch.setattr(remote_login_mod, "ask_user", lambda _agent, question, options: scan_prompts.append((question, options)))
    monkeypatch.setattr(remote_login_mod, "_fill_password", lambda _agent, _browser, question: filled.append(question))

    remote_login_mod._handle_login_step(SimpleNamespace(llm=RaisingLLM()), browser)

    assert filled == ["请输入账号和密码"]
    assert sent_shots == []
    assert scan_prompts == []
