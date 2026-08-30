"""Real ConnectOnion async-core to Onionwright paid-launch contract."""

import time
from types import SimpleNamespace

import pytest

onionwright = pytest.importorskip("onionwright")

from onionwright.paid import Artifact, Capability, PreparedBrowser  # noqa: E402

from connectonion.useful_tools.browser_tools import (  # noqa: E402
    BrowserAutomation,
    engine,
)
from connectonion.useful_tools.browser_tools import (  # noqa: E402
    _async_browser as async_mod,
)


class Page:
    url = "about:blank"

    def is_closed(self):
        return False

    def set_default_navigation_timeout(self, milliseconds):
        pass

    async def set_viewport_size(self, viewport):
        pass


class Context:
    def __init__(self, page):
        self.pages = [page]
        self.handlers = {}
        self.close_calls = 0

    def on(self, event, handler):
        self.handlers[event] = handler

    async def cookies(self):
        return []

    async def add_cookies(self, cookies):
        pass

    async def new_page(self):
        page = Page()
        self.pages.append(page)
        return page

    async def close(self):
        self.close_calls += 1


class Chromium:
    def __init__(self, context):
        self.context = context
        self.calls = []

    async def launch_persistent_context(self, profile, **kwargs):
        self.calls.append((profile, kwargs))
        return self.context


class Playwright:
    def __init__(self, chromium):
        self.chromium = chromium
        self.stop_calls = 0

    async def stop(self):
        self.stop_calls += 1


class Manager:
    def __init__(self, playwright):
        self.playwright = playwright

    async def start(self):
        return self.playwright


class Session:
    def __init__(self, home):
        self.session_id = "00000000-0000-4000-8000-000000000001"
        self.paid_until = int(time.time()) + 900
        self.licence = SimpleNamespace(license_address="0xaccount")
        self.licence_path = home / "sessions" / f"{self.session_id}.json"
        self.licence_path.parent.mkdir(parents=True)
        self.licence_path.write_text("{}")
        self.release_calls = 0

    def release(self):
        self.release_calls += 1


class Client:
    client_version = engine.MIN_ONIONWRIGHT_VERSION
    release_channel = engine.ONIONWRIGHT_RELEASE_CHANNEL

    def __init__(self, home, prepared):
        self.home = home
        self.prepared = prepared
        self.session = Session(home)
        self.start_calls = []

    def start(self, prepared, key):
        self.start_calls.append((prepared, key))
        return self.session


def prepared_browser(tmp_path):
    artifact = Artifact(
        artifact_id=f"chrome/{engine.BROWSER_REVISION}/linux-x86_64.tar.zst",
        browser_revision=engine.BROWSER_REVISION,
        platform_tag="linux-x86_64",
        os="linux",
        architecture="x86_64",
        minimum_os_version="22.04",
        minimum_client_version=engine.MIN_ONIONWRIGHT_VERSION,
        object_key=f"chrome/{engine.BROWSER_REVISION}/linux-x86_64.tar.zst",
        size_bytes=10,
        sha256="1" * 64,
        package_format="tar.zst",
        executable_path="chrome",
        repository_commit="2" * 40,
        provenance_sha256="3" * 64,
        signing_mode="not_applicable",
        notarized=False,
        bundle_path=None,
        signing_identity_sha256=None,
        paid_ready=True,
    )
    capability = Capability(
        requested_engine="onion",
        platform_tag="linux-x86_64",
        host_os_version="22.04",
        architecture="x86_64",
        browser_revision=engine.BROWSER_REVISION,
        client_version=engine.MIN_ONIONWRIGHT_VERSION,
        release_channel=engine.ONIONWRIGHT_RELEASE_CHANNEL,
        artifact=artifact,
        cache_state="ready",
        paid_capable=True,
        reason="ready",
        next_action="start",
        interval_usd="0.025",
    )
    executable = tmp_path / "chrome"
    executable.write_text("exact-browser")
    return PreparedBrowser(capability, executable=executable)


def test_sync_facade_reaches_real_async_paid_boundary(tmp_path, monkeypatch):
    prepared = prepared_browser(tmp_path)
    client = Client(tmp_path, prepared)
    resolution = engine.Resolution(
        requested=engine.ONION,
        resolved=engine.ONION,
        reason=engine.Reason.ONION_READY,
        next_action="start",
        client=client,
        prepared=prepared,
    )
    page = Page()
    context = Context(page)
    chromium = Chromium(context)
    playwright = Playwright(chromium)
    monkeypatch.setattr(async_mod, "ASYNC_BROWSER_AVAILABLE", True)
    monkeypatch.setattr(async_mod, "async_playwright", lambda: Manager(playwright))

    browser = BrowserAutomation(
        engine_mode=engine.ONION,
        engine_resolver=lambda mode: resolution,
    )
    try:
        message = browser.open_browser(headless=True)
        status = browser.engine_status()
    finally:
        closed = browser.close()

    assert "Onion Browser opened" in message
    assert "$0.025 / 15 min" in message
    assert client.start_calls[0][0] is prepared
    assert client.start_calls[0][1].startswith("connectonion-start:")
    profile, kwargs = chromium.calls[0]
    assert profile == str(tmp_path / "profiles" / "0xaccount")
    assert kwargs["executable_path"] == str(prepared.executable)
    assert (
        kwargs["args"][-1] == f"--license-file={client.session.licence_path.resolve()}"
    )
    assert status["resolved_engine"] == engine.ONION
    assert status["interval_usd"] == 0.025
    assert status["paid_session_id"] == client.session.session_id
    assert client.session.release_calls == 1
    assert context.close_calls == 1
    assert playwright.stop_calls == 1
    assert closed == "Browser closed"
