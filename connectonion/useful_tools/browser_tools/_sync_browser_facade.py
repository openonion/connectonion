"""Synchronous compatibility facade over :class:`AsyncBrowserCore`.

The public ``BrowserAutomation`` API predates asyncio.  Its implementation now
uses the async browser driver, but callers still receive ordinary return values:
one private event-loop thread owns the core and every synchronous call is
submitted to that loop with the caller's tab binding.
"""

import asyncio
import functools
import inspect
import threading
from concurrent.futures import Future
from typing import Any, Optional

from ._async_browser import AsyncBrowserCore


class BrowserAutomation:
    """Backward-compatible synchronous browser automation.

    Calls are safe from normal threads and from threads that already run an
    asyncio loop.  Calling a synchronous method from this instance's own runtime
    thread is rejected because waiting there would deadlock the browser loop.
    """

    def __init__(
        self,
        use_chrome_profile: bool = True,
        headless: bool = False,
        seed_state: Optional[str] = None,
        tab_idle_ttl: float = 3600.0,
        max_tabs: int = 10,
    ) -> None:
        self._core_kwargs = {
            "use_chrome_profile": use_chrome_profile,
            "headless": headless,
            "seed_state": seed_state,
            "tab_idle_ttl": tab_idle_ttl,
            "max_tabs": max_tabs,
        }
        self._runtime_lock = threading.RLock()
        self._runtime_ready = threading.Event()
        self._runtime_thread: Optional[threading.Thread] = None
        self._executor_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._core: Optional[AsyncBrowserCore] = None
        self._runtime_error: Optional[BaseException] = None
        self._stopping = False
        self._session_binding = threading.local()
        self.form_data = {}
        self._screenshots = []
        self._ensure_runtime()

    def _run_runtime(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            core = AsyncBrowserCore(**self._core_kwargs)
            with self._runtime_lock:
                self._loop = loop
                self._core = core
                self._executor_thread = threading.current_thread()
                self._runtime_ready.set()
            loop.run_forever()
        except BaseException as exc:
            with self._runtime_lock:
                self._runtime_error = exc
                self._runtime_ready.set()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def _ensure_runtime(self) -> None:
        with self._runtime_lock:
            if self._runtime_thread is not None and self._runtime_thread.is_alive():
                return
            self._runtime_ready = threading.Event()
            self._runtime_error = None
            thread = threading.Thread(
                target=self._run_runtime,
                name=f"browser-async-{id(self):x}",
                daemon=True,
            )
            self._runtime_thread = thread
            thread.start()
        self._runtime_ready.wait()
        if self._runtime_error is not None:
            raise RuntimeError("browser async runtime failed to start") from self._runtime_error

    def _bound_session_key(self):
        return getattr(self._session_binding, "key", None)

    def _bind_session(self, session_id) -> None:
        """Bind subsequent calls on this caller thread to one browser tab."""
        self._session_binding.key = session_id

    def _submit(self, awaitable) -> Any:
        self._ensure_runtime()
        thread, loop = self._runtime_thread, self._loop
        if threading.current_thread() is thread:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise RuntimeError(
                "synchronous BrowserAutomation methods cannot run on their own "
                "async runtime thread"
            )
        if loop is None:
            raise RuntimeError("browser async runtime is not available")
        future: Future = asyncio.run_coroutine_threadsafe(awaitable, loop)
        try:
            return future.result()
        except BaseException:
            future.cancel()
            raise

    def _invoke(self, name: str, *args, _during_stop: bool = False, **kwargs):
        with self._runtime_lock:
            if self._stopping and not _during_stop:
                raise RuntimeError("browser async runtime is closing")
        session = self._bound_session_key()

        async def call():
            core = self._core
            if core is None:
                raise RuntimeError("browser async runtime is not available")
            core._bind_session(session)
            result = getattr(core, name)(*args, **kwargs)
            return await result if inspect.isawaitable(result) else result

        return self._submit(call())

    def _run_on_runtime(self, callback):
        """Run an internal diagnostic callback beside the async core.

        Public browser work should use the stable methods. This seam exists for
        in-repository adapters such as detector harnesses and input plugins that
        must use driver objects without crossing the event-loop thread boundary.
        """
        with self._runtime_lock:
            if self._stopping:
                raise RuntimeError("browser async runtime is closing")
        session = self._bound_session_key()

        async def call():
            core = self._core
            if core is None:
                raise RuntimeError("browser async runtime is not available")
            core._bind_session(session)
            result = callback(core)
            return await result if inspect.isawaitable(result) else result

        return self._submit(call())

    def _read_core_attr(self, name: str, default=None):
        with self._runtime_lock:
            live = (
                not self._stopping
                and self._runtime_thread is not None
                and self._runtime_thread.is_alive()
            )
        if not live:
            return default

        async def read():
            return getattr(self._core, name, default)

        return self._submit(read())

    @property
    def page(self):
        session = self._bound_session_key()
        with self._runtime_lock:
            live = (
                not self._stopping
                and self._runtime_thread is not None
                and self._runtime_thread.is_alive()
            )
        if not live:
            return None

        async def read():
            self._core._bind_session(session)
            return self._core.page

        return self._submit(read())

    @page.setter
    def page(self, value) -> None:
        session = self._bound_session_key()

        async def write():
            self._core._pages[session] = value
            self._core._page_used[session] = asyncio.get_running_loop().time()

        self._submit(write())

    @property
    def browser(self):
        return self._read_core_attr("browser")

    @property
    def playwright(self):
        return self._read_core_attr("playwright")

    @property
    def last_screenshot_path(self):
        return self._read_core_attr("last_screenshot_path")

    @property
    def screenshots_dir(self):
        return self._read_core_attr("screenshots_dir")

    @screenshots_dir.setter
    def screenshots_dir(self, value) -> None:
        async def write():
            self._core.screenshots_dir = value

        self._submit(write())

    @property
    def _pages(self):
        return self._read_core_attr("_pages", {})

    @property
    def _page_used(self):
        return self._read_core_attr("_page_used", {})

    @property
    def _page_url(self):
        return self._read_core_attr("_page_url", {})

    @property
    def _tab_meta(self):
        return self._read_core_attr("_tab_meta", {})

    @property
    def _headless(self):
        return self._read_core_attr("_headless", self._core_kwargs["headless"])

    @property
    def use_chrome_profile(self):
        return self._core_kwargs["use_chrome_profile"]

    def _context_is_alive(self) -> bool:
        return bool(self._invoke("is_alive"))

    def _browser_is_usable(self) -> bool:
        return self._context_is_alive() and self.page is not None

    def _launch_failed(self) -> bool:
        return bool(
            self._read_core_attr("playwright") is not None
            and self._read_core_attr("browser") is None
        )

    def close(self) -> str:
        """Close the bound tab, or fully stop the unbound browser runtime."""
        session = self._bound_session_key()
        with self._runtime_lock:
            live = self._runtime_thread is not None and self._runtime_thread.is_alive()
        if not live:
            return "Browser closed"

        if session is not None:
            result = self._invoke("close")
            if result == "Browser tab closed for this session.":
                return "Closed this session's browser tab."
            return result

        with self._runtime_lock:
            self._stopping = True
        try:
            result = self._invoke("close", _during_stop=True)
            with self._runtime_lock:
                loop, thread = self._loop, self._runtime_thread
                if loop is not None:
                    loop.call_soon_threadsafe(loop.stop)
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=15)
                if thread.is_alive():
                    raise RuntimeError(
                        "browser async runtime did not stop within 15 seconds"
                    )
            with self._runtime_lock:
                self._loop = None
                self._core = None
                self._runtime_thread = None
                self._executor_thread = None
        finally:
            with self._runtime_lock:
                self._stopping = False
        if result == "Browser closed. Session saved for next time.":
            return "Browser closed"
        return result

    def _teardown(self) -> str:
        return self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def _install_sync_methods() -> None:
    """Mirror every public async-core method without duplicating its signature."""
    for name, method in inspect.getmembers(AsyncBrowserCore, inspect.isfunction):
        if (
            name.startswith("_")
            or name in {"close", "is_alive"}
            or not inspect.iscoroutinefunction(method)
        ):
            continue

        @functools.wraps(method)
        def call(self, *args, __name=name, **kwargs):
            return self._invoke(__name, *args, **kwargs)

        setattr(BrowserAutomation, name, call)


_install_sync_methods()


def adopt_legacy_contract(legacy_class) -> None:
    """Copy the established public descriptions onto the facade methods.

    Agent tool schemas and ``co browser help`` consume first-line docstrings, so
    preserving signatures alone is not enough compatibility.
    """
    BrowserAutomation.__doc__ = legacy_class.__doc__
    for name, legacy_method in inspect.getmembers(legacy_class, inspect.isfunction):
        if name.startswith("_") or not hasattr(BrowserAutomation, name):
            continue
        method = getattr(BrowserAutomation, name)
        method.__doc__ = legacy_method.__doc__
        method.__signature__ = inspect.signature(legacy_method)
