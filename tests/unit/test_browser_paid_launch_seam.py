from types import SimpleNamespace

from connectonion.useful_tools.browser_tools import browser as mod
from connectonion.useful_tools.browser_tools import engine


class FakePage:
    url = "about:blank"

    def is_closed(self):
        return False

    def close(self):
        pass

    def wait_for_timeout(self, milliseconds):
        pass


class FakeContext:
    def __init__(self, page=None):
        self.pages = [page] if page else []
        self.closed = 0

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    def cookies(self):
        return []

    def close(self):
        self.closed += 1


class FakePlaywright:
    def __init__(self, context=None):
        self.context = context
        self.stopped = 0
        self.chromium = SimpleNamespace(
            launch_persistent_context=lambda *args, **kwargs: self.context,
        )

    def stop(self):
        self.stopped += 1


class FakeManager:
    def __init__(self, playwright):
        self.playwright = playwright

    def start(self):
        return self.playwright


class FakePaidRun:
    def __init__(self):
        self.page = FakePage()
        self.closable = FakeContext(self.page)
        self.session = SimpleNamespace(
            session_id="paid-session",
            paid_until=1234,
            licence=SimpleNamespace(license_address="0xaccount"),
        )
        self.terminal_reason = None
        self.close_calls = 0

    def close(self):
        self.close_calls += 1
        self.closable.close()


def onion_resolution():
    return engine.Resolution(
        requested=engine.AUTO,
        resolved=engine.ONION,
        reason=engine.Reason.ONION_READY,
        next_action="start",
        client=object(),
        prepared=SimpleNamespace(
            capability=SimpleNamespace(
                artifact=SimpleNamespace(artifact_id="chrome/150/darwin-arm64.tar.zst")
            )
        ),
    )


def test_real_launch_seam_uses_supervised_paid_handle(monkeypatch):
    paid = FakePaidRun()
    playwright = FakePlaywright()
    calls = []
    monkeypatch.setattr(mod, "BROWSER_AVAILABLE", True)
    monkeypatch.setattr(mod, "sync_playwright", lambda: FakeManager(playwright))

    def launch(resolution, owner, key, **kwargs):
        calls.append((resolution, owner, key, kwargs))
        return paid

    monkeypatch.setattr(mod.browser_engine, "launch", launch)
    browser = mod.BrowserAutomation(engine_resolver=lambda mode: onion_resolution())

    message = browser.open_browser()
    status = browser.engine_status()
    closed = browser.close()

    assert "Onion Browser opened" in message
    assert len(calls) == 1
    assert calls[0][1] is playwright
    assert calls[0][2].startswith("connectonion-start:")
    assert calls[0][3]["user_data_dir"] is True
    assert status["resolved_engine"] == engine.ONION
    assert status["artifact_id"] == "chrome/150/darwin-arm64.tar.zst"
    assert status["paid_session_id"] == "paid-session"
    assert paid.close_calls == 1
    assert playwright.stopped == 1
    assert closed == "Browser closed"


def test_paid_launch_failure_never_hot_swaps_to_system(monkeypatch):
    playwright = FakePlaywright()
    monkeypatch.setattr(mod, "BROWSER_AVAILABLE", True)
    monkeypatch.setattr(mod, "sync_playwright", lambda: FakeManager(playwright))
    monkeypatch.setattr(
        mod.browser_engine,
        "launch",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("paid launch failed")),
    )
    browser = mod.BrowserAutomation(engine_resolver=lambda mode: onion_resolution())

    try:
        browser.open_browser()
    except RuntimeError as exc:
        assert str(exc) == "paid launch failed"
    else:
        raise AssertionError("paid launch failure was swallowed")

    assert browser.browser is None
    assert browser.playwright is None
    assert playwright.stopped == 1
