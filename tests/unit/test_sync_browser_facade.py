"""Contract tests for the public sync facade over the async browser core."""

import asyncio
import contextvars
import inspect
import threading

import pytest

from connectonion.useful_tools.browser_tools import BrowserAutomation as PublicBrowserAutomation
from connectonion.useful_tools.browser_tools import _sync_browser_facade as facade
from connectonion.useful_tools.browser_tools.browser import LegacyBrowserAutomation


class FakeAsyncCore:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.session = contextvars.ContextVar("fake_browser_session", default=None)
        self.calls = []
        self.browser = object()
        self.playwright = object()
        self._pages = {}
        self._page_used = {}
        self._page_url = {}
        self._tab_meta = {}
        self._headless = kwargs["headless"]
        self.screenshots_dir = ".tmp"
        self.last_screenshot_path = None

    def _bind_session(self, session):
        self.session.set(session)

    async def tab_status(self):
        await asyncio.sleep(0)
        call = (self.session.get(), threading.current_thread())
        self.calls.append(call)
        return f"tab:{call[0]}"

    async def close(self):
        await asyncio.sleep(0)
        if self.session.get() is not None:
            return "Browser tab closed for this session."
        self.browser = None
        self.playwright = None
        return "Browser closed. Session saved for next time."


@pytest.fixture
def browser(monkeypatch):
    monkeypatch.setattr(facade, "AsyncBrowserCore", FakeAsyncCore)
    value = facade.BrowserAutomation(headless=True)
    try:
        yield value
    finally:
        value._bind_session(None)
        value.close()


def test_public_surface_and_signatures_stay_identical():
    assert PublicBrowserAutomation is facade.BrowserAutomation
    legacy = {
        name: method
        for name, method in inspect.getmembers(
            LegacyBrowserAutomation, inspect.isfunction
        )
        if not name.startswith("_")
    }
    public = {
        name: method
        for name, method in inspect.getmembers(facade.BrowserAutomation, inspect.isfunction)
        if not name.startswith("_")
    }

    assert set(public) == set(legacy)
    for name, method in public.items():
        assert inspect.signature(method) == inspect.signature(legacy[name]), name


def test_sync_call_from_running_event_loop_is_defined(browser):
    async def caller():
        return browser.tab_status()

    assert asyncio.run(caller()) == "tab:None"
    assert browser._core.calls[0][1] is browser._runtime_thread


def test_session_binding_crosses_the_thread_boundary(browser):
    browser._bind_session("checkout")

    assert browser.tab_status() == "tab:checkout"


def test_internal_detector_callback_stays_on_the_runtime(browser):
    browser._bind_session("detector")

    session, thread = browser._run_on_runtime(
        lambda core: (core.session.get(), threading.current_thread())
    )

    assert session == "detector"
    assert thread is browser._runtime_thread


def test_call_from_owned_runtime_thread_fails_instead_of_deadlocking(browser):
    done = threading.Event()
    outcome = []

    def call_on_runtime():
        try:
            browser.tab_status()
        except Exception as exc:
            outcome.append(exc)
        finally:
            done.set()

    browser._loop.call_soon_threadsafe(call_on_runtime)

    assert done.wait(2)
    assert isinstance(outcome[0], RuntimeError)
    assert "own async runtime thread" in str(outcome[0])


def test_bound_close_keeps_runtime_and_unbound_close_stops_it(browser):
    thread = browser._runtime_thread
    browser._bind_session("one")

    assert browser.close() == "Closed this session's browser tab."
    assert thread.is_alive()

    browser._bind_session(None)
    assert browser.close() == "Browser closed"
    assert not thread.is_alive()
    assert browser.close() == "Browser closed"


def test_repeated_create_and_close_leaves_no_runtime_thread(monkeypatch):
    monkeypatch.setattr(facade, "AsyncBrowserCore", FakeAsyncCore)
    threads = []

    for _ in range(5):
        browser = facade.BrowserAutomation()
        threads.append(browser._runtime_thread)
        assert browser.close() == "Browser closed"

    assert all(not thread.is_alive() for thread in threads)
