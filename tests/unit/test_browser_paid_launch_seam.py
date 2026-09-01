from types import SimpleNamespace

import pytest

from connectonion.useful_tools.browser_tools import _async_browser as async_mod
from connectonion.useful_tools.browser_tools import browser as mod
from connectonion.useful_tools.browser_tools import engine


class FakePage:
    def __init__(self):
        self.url = "about:blank"

    def is_closed(self):
        return False

    def close(self):
        self.closed = True

    def set_default_navigation_timeout(self, milliseconds):
        pass

    async def set_viewport_size(self, viewport):
        pass

    async def goto(self, url, **_kwargs):
        self.url = url

    async def wait_for_timeout(self, milliseconds):
        pass


class FakeContext:
    def __init__(self, page=None):
        self.pages = [page] if page else []
        self.closed = 0

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page

    async def cookies(self):
        return []

    async def close(self):
        self.closed += 1


class FakePlaywright:
    def __init__(self, context=None):
        self.context = context
        self.stopped = 0
        self.chromium = SimpleNamespace(
            launch_persistent_context=lambda *args, **kwargs: self.context,
        )

    async def stop(self):
        self.stopped += 1


class FakeManager:
    def __init__(self, playwright):
        self.playwright = playwright

    async def start(self):
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

    async def close(self):
        self.close_calls += 1
        await self.closable.close()


def onion_resolution(requested):
    return engine.Resolution(
        requested=requested,
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
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))

    async def launch(resolution, owner, key, **kwargs):
        calls.append((resolution, owner, key, kwargs))
        return paid

    monkeypatch.setattr(async_mod.browser_engine, "launch_async", launch)
    browser = mod.BrowserAutomation(
        engine_mode=engine.ONION,
        engine_resolver=lambda mode: onion_resolution(mode),
    )

    message = browser.open_browser()
    status = browser.engine_status()
    closed = browser.close()

    assert "WTFbrowser opened" in message
    assert len(calls) == 1
    assert calls[0][0].requested == engine.ONION
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
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))

    async def fail(*args, **kwargs):
        raise RuntimeError("paid launch failed")

    monkeypatch.setattr(
        async_mod.browser_engine,
        "launch_async",
        fail,
    )
    browser = mod.BrowserAutomation(
        engine_mode=engine.ONION,
        engine_resolver=lambda mode: onion_resolution(mode),
    )

    try:
        browser.open_browser()
    except RuntimeError as exc:
        assert str(exc) == "paid launch failed"
    else:
        raise AssertionError("paid launch failure was swallowed")

    assert browser.browser is None
    assert browser.playwright is None
    assert playwright.stopped == 1


def test_a_retried_launch_does_not_buy_a_second_interval(monkeypatch):
    """A failed launch must not charge again on the next attempt.

    The server mints the licence inside launch_async, so a launch that fails
    afterwards — a transient RPC error, a driver that will not start, a
    boundary that cannot be proven — has already been paid for. A fresh
    idempotency key each attempt buys a fresh 15-minute interval each attempt,
    and on a machine where the launch can never succeed that bills forever
    while every command fails.
    """
    playwright = FakePlaywright()
    keys = []
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))

    async def fail_after_minting(resolution, owner, key, **kwargs):
        keys.append(key)
        raise RuntimeError("launched, charged, then died")

    monkeypatch.setattr(async_mod.browser_engine, "launch_async", fail_after_minting)
    browser = mod.BrowserAutomation(
        engine_mode=engine.ONION,
        engine_resolver=lambda mode: onion_resolution(mode),
    )

    for _ in range(3):
        try:
            browser.open_browser()
        except RuntimeError:
            pass

    assert len(keys) == 3
    assert len(set(keys)) == 1, f"each retry bought its own interval: {keys}"


def test_a_deliberate_close_starts_a_new_billing_interval(monkeypatch):
    """Retries replay one session; a real close ends it."""
    playwright = FakePlaywright()
    keys = []
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))

    async def launch(resolution, owner, key, **kwargs):
        keys.append(key)
        return FakePaidRun()

    monkeypatch.setattr(async_mod.browser_engine, "launch_async", launch)
    browser = mod.BrowserAutomation(
        engine_mode=engine.ONION,
        engine_resolver=lambda mode: onion_resolution(mode),
    )

    browser.open_browser()
    browser.close()
    browser.open_browser()
    browser.close()

    assert len(keys) == 2
    assert len(set(keys)) == 2, "a closed session replayed its own paid interval"


def test_a_paid_session_says_what_it_costs(monkeypatch):
    """Explicit ``auto`` may buy Onion, and must state the interval price."""
    playwright = FakePlaywright()
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))

    async def launch(resolution, owner, key, **kwargs):
        return FakePaidRun()

    monkeypatch.setattr(async_mod.browser_engine, "launch_async", launch)

    priced = onion_resolution(engine.AUTO)
    # The real Onionwright Capability carries wire money as a decimal string.
    priced.prepared.capability.interval_usd = "0.025"
    browser = mod.BrowserAutomation(
        engine_mode=engine.AUTO,
        engine_resolver=lambda mode: priced,
    )

    message = browser.open_browser()
    status = browser.engine_status()
    browser.close()

    assert "$0.025 / 15 min" in message
    assert status["requested_engine"] == engine.AUTO
    assert status["resolved_engine"] == engine.ONION
    assert status["interval_usd"] == 0.025


@pytest.mark.parametrize("action", ["go_to", "newtab"])
def test_the_first_paid_page_action_keeps_the_interval_price(monkeypatch, action):
    playwright = FakePlaywright()
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))

    async def launch(resolution, owner, key, **kwargs):
        return FakePaidRun()

    monkeypatch.setattr(async_mod.browser_engine, "launch_async", launch)
    priced = onion_resolution(engine.ONION)
    priced.prepared.capability.interval_usd = "0.025"
    browser = mod.BrowserAutomation(
        engine_mode=engine.ONION,
        engine_resolver=lambda mode: priced,
    )

    if action == "go_to":
        message = browser.go_to("example.com", purpose="test", who="tester")
    else:
        message = browser.newtab(
            "example.com", purpose="test", who="tester"
        )
    browser.close()

    assert "$0.025 / 15 min" in message
    assert "Navigated to https://example.com" in message


def test_status_names_the_browser_that_actually_runs(monkeypatch):
    """A paid resolution runs the downloaded artifact, not the driver default.

    Measured on a real server: status read `/usr/bin/google-chrome` while every
    page was served by a Chromium under `.onionwright/runtimes`. The line
    exists to answer "which binary is serving my pages"; naming a different one
    is worse than printing nothing.
    """
    playwright = FakePlaywright()
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: FakeManager(playwright))

    async def launch(resolution, owner, key, **kwargs):
        return FakePaidRun()

    monkeypatch.setattr(async_mod.browser_engine, "launch_async", launch)

    resolution = onion_resolution(engine.ONION)
    resolution.prepared.executable = "/runtimes/7de5a8/chrome"
    browser = mod.BrowserAutomation(
        engine_mode=engine.ONION,
        engine_resolver=lambda mode: resolution,
    )

    browser.open_browser()
    status = browser.engine_status()
    browser.close()

    assert status["executable"] == "/runtimes/7de5a8/chrome"


def test_a_terminated_paid_session_refuses_page_commands():
    """Once Onionwright reports terminal_reason, the browser must stop serving.

    The context can outlive the paid session — expiry, revocation, non-payment.
    Serving page verbs against it is an unpaid browser treated as paid. The
    reason was only ever shown in status; nothing acted on it.
    """
    core = async_mod.AsyncBrowserCore.__new__(async_mod.AsyncBrowserCore)
    core._paid_run = FakePaidRun()

    # A live session lets the guard pass.
    core._paid_run.terminal_reason = None
    core._require_live_paid_session()

    # A terminated one refuses, carrying the reason.
    core._paid_run.terminal_reason = "revoked"
    with pytest.raises(async_mod.PaidSessionEndedError) as raised:
        core._require_live_paid_session()
    assert raised.value.reason == "revoked"

    # A free/system session (no paid run) is never gated.
    core._paid_run = None
    core._require_live_paid_session()


def test_the_guard_is_called_from_the_page_command_entry_point():
    """The check must run where page commands enter, not sit unreferenced.

    _tab_operation is the single gate every page verb passes through. A guard
    defined but never called is exactly the terminal_reason situation this
    fixes, so assert the call is there rather than trusting it.
    """
    import inspect

    source = inspect.getsource(async_mod.AsyncBrowserCore._tab_operation)
    assert "_require_live_paid_session()" in source
