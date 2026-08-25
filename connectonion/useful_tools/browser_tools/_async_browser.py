"""
Purpose: Internal Patchright async browser core for the 1.8 driver migration.
LLM-Note:
  Dependencies: imports only patchright.async_api plus browser_config/chrome_finder and stdlib | imported by [future async daemon/runtime; tests during migration] | tested by [tests/unit/test_async_browser_core.py]
  Data flow: caller binds a session in a ContextVar → each async operation acquires that tab's lock → the shared persistent context lazily creates/restores one page per session → independent tab operations may interleave on one event loop
  State/Effects: persistent profile at $CO_BROWSER_PROFILE_DIR or ~/.co/browser_profile | one shared BrowserContext | per-session pages/metadata/restore URLs | cancellation-safe context and driver teardown
  Integration: internal AsyncBrowserCore; the public synchronous BrowserAutomation remains unchanged until #500 adds its compatibility facade
  Errors: live profile ownership fails before driver start | launch/cancellation tears down partially-created driver state | destructive keyboard shortcuts fail closed outside editable focus

This module is deliberately internal while #498 is in progress. It must never
import or call patchright.sync_api: the old public class remains the compatibility
implementation until the async contract is complete and #500 installs the facade.
"""

import asyncio
import base64
import contextvars
import json
import os
import platform
import time
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .browser_config import CHROME_DEFAULT_ARGS, IGNORE_DEFAULT_ARGS
from .chrome_finder import find_system_chrome

try:
    from patchright.async_api import BrowserContext, Page, Playwright, async_playwright

    ASYNC_BROWSER_AVAILABLE = True
except ImportError:
    BrowserContext = Page = Playwright = Any
    async_playwright = None
    ASYNC_BROWSER_AVAILABLE = False


_FOCUSED_ELEMENT_SCRIPT = """
(previewLimit) => {
    let element = document.activeElement;
    while (element && element.shadowRoot && element.shadowRoot.activeElement) {
        element = element.shadowRoot.activeElement;
    }
    if (!element) {
        return {
            tag: null, type: null, id: null, name: null, role: null,
            aria_label: null, contenteditable: null, is_editable: false,
            disabled: false, read_only: false, sensitive: false,
            value_preview: null, value_truncated: false,
        };
    }

    const tag = element.tagName.toLowerCase();
    const type = (element.getAttribute('type') || '').toLowerCase() || null;
    const disabled = Boolean(element.disabled);
    const readOnly = Boolean(element.readOnly);
    const nonTextInputTypes = new Set([
        'button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio',
        'range', 'reset', 'submit',
    ]);
    const textInput = tag === 'input' && !nonTextInputTypes.has(type || 'text');
    const isEditable = !disabled && !readOnly && (
        textInput || tag === 'textarea' || element.isContentEditable
    );
    const sensitive = tag === 'input' && type === 'password';
    let value = null;
    if (!sensitive && (tag === 'input' || tag === 'textarea')) {
        value = String(element.value || '');
    } else if (!sensitive && element.isContentEditable) {
        value = String(element.innerText || element.textContent || '');
    }

    return {
        tag,
        type,
        id: element.id || null,
        name: element.getAttribute('name'),
        role: element.getAttribute('role'),
        aria_label: element.getAttribute('aria-label'),
        contenteditable: element.getAttribute('contenteditable'),
        is_editable: isEditable,
        disabled,
        read_only: readOnly,
        sensitive,
        value_preview: value === null ? null : value.slice(0, previewLimit),
        value_truncated: value === null ? false : value.length > previewLimit,
    };
}
"""


def _profile_dir() -> Path:
    configured = os.environ.get("CO_BROWSER_PROFILE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path.home() / ".co" / "browser_profile"


def _headless_without_display(headless: bool) -> bool:
    if headless or platform.system() != "Linux":
        return headless
    return not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _clear_stale_profile_lock(profile_dir: Path) -> None:
    lock = profile_dir / "SingletonLock"
    if not lock.is_symlink():
        return
    tail = os.readlink(lock).rsplit("-", 1)[-1]
    if not tail.isdigit() or _pid_alive(int(tail)):
        return
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        (profile_dir / name).unlink(missing_ok=True)


def _profile_lock_holder(profile_dir: Path) -> Optional[int]:
    lock = profile_dir / "SingletonLock"
    if not lock.is_symlink():
        return None
    tail = os.readlink(lock).rsplit("-", 1)[-1]
    if not tail.isdigit():
        return None
    pid = int(tail)
    return pid if _pid_alive(pid) else None


def _proxy_from_env() -> Optional[Dict[str, str]]:
    url = os.environ.get("BROWSER_PROXY", "").strip()
    if not url:
        return None
    parsed = urllib.parse.urlparse(url)
    server = f"{parsed.scheme}://{parsed.hostname}"
    if parsed.port:
        server += f":{parsed.port}"
    proxy = {"server": server}
    if parsed.username:
        proxy["username"] = urllib.parse.unquote(parsed.username)
    if parsed.password:
        proxy["password"] = urllib.parse.unquote(parsed.password)
    return proxy


def _requires_editable_focus(key: str) -> bool:
    parts = [part.strip().casefold() for part in key.split("+") if part.strip()]
    if not parts:
        return False
    if parts[-1] in {"backspace", "delete"}:
        return True
    return parts[-1] == "a" and bool(
        set(parts[:-1]).intersection({"control", "ctrl", "meta", "controlormeta"})
    )


def _normalize_url(url: str) -> str:
    if url.startswith(("http://", "https://", "file://", "about:", "data:", "chrome://")):
        return url
    return f"https://{url}" if "." in url else f"http://{url}"


def _occupancy_help(verb: str, url: str) -> str:
    return (
        "This tab has no purpose yet — say why you're using it. "
        "(This message is for the AI agent, not the user.)\n\n"
        "Call again with these filled in from what the user asked you to do:\n"
        f'  {verb}("{url}", purpose="<why you\'re opening this tab>", '
        'who="<the user this is for>", hours=<how long you\'ll need it>)'
    )


async def _complete_cleanup(awaitable):
    """Finish cleanup even if the caller is cancelled while awaiting it.

    `asyncio.shield()` alone returns immediately on caller cancellation while the
    cleanup task continues in the background. That is not deterministic shutdown:
    a new runtime could open the same profile before the old context has released
    it. Keep awaiting the shielded task and report whether cancellation interrupted
    the caller so the outer lifecycle operation can re-raise after cleanup finishes.
    """
    task = asyncio.ensure_future(awaitable)
    interrupted = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            interrupted = True
            if task.done():
                break
    if task.cancelled():
        raise asyncio.CancelledError
    return task.result(), interrupted


class AsyncBrowserCore:
    """Internal async browser runtime with one persistent context and one tab per session."""

    def __init__(
        self,
        use_chrome_profile: bool = True,
        headless: bool = False,
        seed_state: Optional[str] = None,
        tab_idle_ttl: float = 3600.0,
        max_tabs: int = 10,
        use_mock_keychain: bool = False,
    ) -> None:
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[BrowserContext] = None
        self._pages: Dict[Optional[str], Page] = {}
        self._page_used: Dict[Optional[str], float] = {}
        self._page_url: Dict[Optional[str], str] = {}
        self._tab_meta: Dict[Optional[str], Dict[str, Any]] = {}
        self._tab_idle_ttl = tab_idle_ttl
        self._max_tabs = max_tabs
        self._max_url_memory = 200
        self.use_chrome_profile = use_chrome_profile
        self._headless = _headless_without_display(headless)
        self._seed_state = seed_state
        self._seeded = False
        self._use_mock_keychain = use_mock_keychain
        self.current_url = ""
        self.screenshots_dir = str(Path.cwd() / ".tmp")
        self.last_screenshot_path: Optional[str] = None

        suffix = hex(id(self))
        self._session_key = contextvars.ContextVar(f"co_browser_session_{suffix}", default=None)
        self._operation_depth = contextvars.ContextVar(f"co_browser_depth_{suffix}", default=0)
        self._lifecycle_lock = asyncio.Lock()
        self._page_state_lock = asyncio.Lock()
        self._tab_locks: Dict[Optional[str], asyncio.Lock] = {}
        self._operation_state_lock = asyncio.Lock()
        self._operations_idle = asyncio.Event()
        self._operations_idle.set()
        self._close_complete = asyncio.Event()
        self._close_complete.set()
        self._active_operations = 0
        self._closing = False
        self._lifecycle_generation = 0

    def _bind_session(self, session_id: Optional[str]) -> None:
        """Bind subsequent calls in the current asyncio context to one session tab."""
        self._session_key.set(session_id)

    def _bound_session_key(self) -> Optional[str]:
        return self._session_key.get()

    @property
    def page(self) -> Optional[Page]:
        return self._pages.get(self._bound_session_key())

    def _tab_lock(self, key: Optional[str]) -> asyncio.Lock:
        lock = self._tab_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._tab_locks[key] = lock
        return lock

    @asynccontextmanager
    async def _tab_operation(self, *, ensure_page: bool = True):
        """Serialize one tab while allowing independent tabs to make progress."""
        depth = self._operation_depth.get()
        if depth:
            yield
            return

        key = self._bound_session_key()
        async with self._tab_lock(key):
            async with self._operation_state_lock:
                if self._closing:
                    raise RuntimeError("Browser runtime is closing")
                self._active_operations += 1
                self._operations_idle.clear()
            token = self._operation_depth.set(depth + 1)
            try:
                if ensure_page and self.browser is not None:
                    await self._ensure_page(key)
                yield
            finally:
                self._operation_depth.reset(token)
                async with self._operation_state_lock:
                    self._active_operations -= 1
                    if self._active_operations == 0:
                        self._operations_idle.set()

    async def _ensure_page(self, key: Optional[str]) -> None:
        if self.browser is None:
            return
        async with self._page_state_lock:
            page = self._pages.get(key)
            if page is None or page.is_closed():
                claimed = {id(candidate) for candidate in self._pages.values()}
                page = None
                for candidate in list(getattr(self.browser, "pages", [])):
                    try:
                        usable = not candidate.is_closed()
                    except Exception:
                        usable = False
                    if usable and id(candidate) not in claimed:
                        page = candidate
                        break
                if page is None:
                    page = await self.browser.new_page()
                page.set_default_navigation_timeout(60000)
                await page.set_viewport_size({"width": 1920, "height": 1200})
                restore_url = self._page_url.get(key)
                if restore_url:
                    try:
                        await page.goto(restore_url, wait_until="domcontentloaded", timeout=30000)
                    except Exception:
                        pass
                self._pages[key] = page
            self._page_used[key] = time.monotonic()
            await self._reclaim_idle_tabs(key)

    async def _reclaim_idle_tabs(self, active_key: Optional[str]) -> None:
        now = time.monotonic()
        expired = [
            key
            for key, last_used in list(self._page_used.items())
            if key != active_key and now - last_used > self._tab_idle_ttl
        ]
        for key in expired:
            await self._reclaim_tab(key)
        if len(self._pages) > self._max_tabs:
            lru = sorted(
                (key for key in self._pages if key != active_key),
                key=lambda key: self._page_used.get(key, 0.0),
            )
            for key in lru[: len(self._pages) - self._max_tabs]:
                await self._reclaim_tab(key)

    async def _reclaim_tab(self, key: Optional[str]) -> Optional[str]:
        page = self._pages.pop(key, None)
        self._page_used.pop(key, None)
        if page is None:
            return None
        try:
            url = page.url
        except Exception:
            url = None
        if url:
            self._page_url.pop(key, None)
            self._page_url[key] = url
            while len(self._page_url) > self._max_url_memory:
                self._page_url.pop(next(iter(self._page_url)))
        try:
            await page.close()
        except Exception as exc:
            return f"close page failed: {exc}"
        return None

    async def _release_tab(self, key: Optional[str]) -> Optional[str]:
        page = self._pages.pop(key, None)
        self._page_used.pop(key, None)
        self._page_url.pop(key, None)
        self._tab_meta.pop(key, None)
        if page is None:
            return None
        try:
            await page.close()
        except Exception as exc:
            return f"close page failed: {exc}"
        return None

    async def is_alive(self) -> bool:
        """Use a driver round-trip; local Page flags remain stale after process death."""
        if self.browser is None:
            return False
        try:
            await self.browser.cookies()
        except Exception:
            return False
        return True

    async def open_browser(self, headless: Optional[bool] = None, force: bool = False) -> str:
        """Open/reuse the runtime while participating in tab and shutdown admission."""
        if self._operation_depth.get():
            return await self._open_browser(headless=headless, force=force)
        async with self._tab_operation(ensure_page=False):
            return await self._open_browser(headless=headless, force=force)

    async def _open_browser(self, headless: Optional[bool] = None, force: bool = False) -> str:
        if headless is None:
            headless = self._headless
        if not ASYNC_BROWSER_AVAILABLE:
            return "Browser tools not installed. Run: pip install patchright && patchright install chrome"

        async with self._operation_state_lock:
            if self._closing:
                raise RuntimeError("Browser runtime is closing")
            generation = self._lifecycle_generation

        async with self._lifecycle_lock:
            async with self._operation_state_lock:
                if self._closing or generation != self._lifecycle_generation:
                    raise RuntimeError("Browser runtime closed while open was waiting")
            key = self._bound_session_key()
            if self.browser is not None:
                try:
                    await self._ensure_page(key)
                except Exception:
                    pass

            if await self.is_alive():
                if not force:
                    return "<system-reminder>Browser already open and usable. Continue using the current browser page.</system-reminder>"
                if key is not None:
                    await self._reclaim_tab(key)
                    self._page_url.pop(key, None)
                    await self._ensure_page(key)
                    return "Opened a fresh tab for this session."
                await self._teardown_unlocked()
                had_previous_state = True
            else:
                had_previous_state = bool(self.browser or self.playwright or self._pages)
                if had_previous_state:
                    await self._teardown_unlocked()

            profile_dir = _profile_dir()
            profile_dir.mkdir(parents=True, exist_ok=True)
            _clear_stale_profile_lock(profile_dir)
            holder = _profile_lock_holder(profile_dir)
            if holder is not None:
                raise RuntimeError(
                    f"Browser profile is already in use by another process (PID {holder}).\n"
                    f"The persistent profile at {profile_dir} can be driven by only one browser at a time."
                )

            manager = async_playwright()
            playwright = None
            context = None
            try:
                start_task = asyncio.create_task(
                    asyncio.wait_for(manager.start(), timeout=30)
                )
                try:
                    playwright = await asyncio.shield(start_task)
                except asyncio.CancelledError:
                    playwright, _ = await _complete_cleanup(start_task)
                    raise

                launch_task = asyncio.create_task(
                    playwright.chromium.launch_persistent_context(
                        str(profile_dir),
                        headless=headless,
                        executable_path=find_system_chrome(),
                        args=CHROME_DEFAULT_ARGS,
                        ignore_default_args=(
                            IGNORE_DEFAULT_ARGS
                            if self._use_mock_keychain
                            else IGNORE_DEFAULT_ARGS + ["--use-mock-keychain"]
                        ),
                        no_viewport=True,
                        proxy=_proxy_from_env(),
                        timeout=120000,
                    )
                )
                try:
                    context = await asyncio.shield(launch_task)
                except asyncio.CancelledError:
                    context, _ = await _complete_cleanup(launch_task)
                    raise
                self.playwright = playwright
                self.browser = context

                if self._seed_state and not self._seeded:
                    cookies = json.loads(
                        Path(self._seed_state).read_text(encoding="utf-8")
                    ).get("cookies", [])
                    if cookies:
                        await context.add_cookies(cookies)
                    self._seeded = True

                await self._ensure_page(key)
            except BaseException:
                self.browser = None
                self.playwright = None
                if context is not None:
                    try:
                        await _complete_cleanup(
                            asyncio.wait_for(context.close(), timeout=30)
                        )
                    except BaseException:
                        pass
                if playwright is not None:
                    try:
                        await _complete_cleanup(
                            asyncio.wait_for(playwright.stop(), timeout=30)
                        )
                    except BaseException:
                        pass
                raise

            if force and had_previous_state:
                return f"Previous browser closed by force. Browser opened with persistent profile: {profile_dir}"
            if had_previous_state:
                return f"Previous stale browser state closed. Browser opened with persistent profile: {profile_dir}"
            return f"Browser opened with persistent profile: {profile_dir}"

    async def save_state(self, path: str) -> str:
        async with self._tab_operation(ensure_page=False):
            if self.browser is None:
                return "Browser not open"
            await self.browser.storage_state(path=path)
            return (
                f"Saved login state to {path}. This file contains live session cookies — "
                "keep it secret, add it to .gitignore, and never commit or bake it into an image."
            )

    async def go_to(
        self,
        url: str,
        purpose: str = "",
        who: str = "",
        hours: float = 0.0,
    ) -> str:
        async with self._tab_operation():
            key = self._bound_session_key()
            existing = self._tab_meta.get(key, {})
            occupied = bool(existing.get("purpose") and existing.get("who"))
            if not occupied and not (purpose and who):
                raise ValueError(_occupancy_help("go_to", url))
            if self.page is None:
                await self.open_browser()

            await self.page.goto(_normalize_url(url), wait_until="domcontentloaded", timeout=30000)
            await self.page.wait_for_timeout(2000)
            self.current_url = self.page.url
            meta = self._tab_meta.setdefault(
                key,
                {"who": "", "purpose": "", "hours": 0.0, "opened_at": datetime.now()},
            )
            if purpose:
                meta["purpose"] = purpose
            if who:
                meta["who"] = who
            if hours:
                meta["hours"] = hours
            await self._save_context()
            return f"Navigated to {self.current_url}"

    async def newtab(
        self,
        url: str = "",
        purpose: str = "",
        who: str = "",
        hours: float = 0.0,
    ) -> str:
        if not purpose or not who:
            raise ValueError(_occupancy_help("newtab", url or "<url>"))
        async with self._tab_operation(ensure_page=False):
            if self.browser is None:
                await self.open_browser()
            key = self._bound_session_key()
            await self._ensure_page(key)
            meta = self._tab_meta.setdefault(key, {"opened_at": datetime.now()})
            meta.update({"who": who, "purpose": purpose})
            if hours:
                meta["hours"] = hours
            if url:
                return await self.go_to(url, purpose=purpose, who=who, hours=hours)
            return f"Opened new tab · who={who} · purpose={purpose!r}"

    async def close_tab(self, key: Optional[str] = None) -> str:
        if key is None:
            key = self._bound_session_key()
        elif key == "main":
            key = None
        async with self._tab_lock(key):
            if key not in self._pages and key not in self._tab_meta:
                return f"No open tab for {key!r}" if self.browser else "Browser not open"
            error = await self._release_tab(key)
            return error or "Tab closed"

    async def get_current_url(self) -> str:
        async with self._tab_operation():
            return self.page.url if self.page else "Browser not open"

    async def get_text(self) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            return await self.page.locator("body").inner_text()

    async def get_focused_element(self, value_preview_chars: int = 160) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            limit = max(0, min(int(value_preview_chars), 1000))
            focused = await self.page.evaluate(_FOCUSED_ELEMENT_SCRIPT, limit)
            return json.dumps(focused, indent=2, ensure_ascii=False, sort_keys=True)

    async def keyboard_press(self, key: str, allow_non_editable: bool = False) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            if _requires_editable_focus(key) and not allow_non_editable:
                focused = await self.page.evaluate(_FOCUSED_ELEMENT_SCRIPT, 160)
                if not focused.get("is_editable", False):
                    return (
                        f"Refused '{key}': the focused element is not editable. "
                        "Focus the intended input and call get_focused_element() before retrying. "
                        "For an intentional page-level shortcut, pass allow_non_editable=True.\n"
                        + json.dumps(focused, ensure_ascii=False, sort_keys=True)
                    )
            await self.page.keyboard.press(key)
            return f"Pressed: '{key}'"

    async def click_element_by_selector(self, selector: str, index: int = 0) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            locator = self.page.locator(selector)
            count = await locator.count()
            if index < 0 or index >= count:
                return f"No element {index + 1}/{count} matching selector: {selector}"
            await locator.nth(index).click()
            return f"Clicked element {index + 1}/{count} matching selector: {selector}"

    async def count_elements_by_selector(self, selector: str) -> int:
        async with self._tab_operation():
            if self.page is None:
                return 0
            return await self.page.locator(selector).count()

    async def get_element_text_by_selector(self, selector: str, index: int = 0) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            locator = self.page.locator(selector)
            count = await locator.count()
            if index < 0 or index >= count:
                return f"No element {index + 1}/{count} matching selector: {selector}"
            return await locator.nth(index).inner_text()

    async def fill_text_by_selector(self, selector: str, text: str, index: int = 0) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            locator = self.page.locator(selector)
            count = await locator.count()
            if index < 0 or index >= count:
                return f"No element {index + 1}/{count} matching selector: {selector}"
            await locator.nth(index).fill(text)
            return f"Filled element {index + 1}/{count} matching selector: {selector}"

    async def upload_file_by_selector(self, selector: str, file_path: str, index: int = 0) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            path = Path(file_path).expanduser().resolve()
            if not path.is_file():
                return f"File not found: {path}"
            locator = self.page.locator(selector)
            count = await locator.count()
            if index < 0 or index >= count:
                return f"No element {index + 1}/{count} matching selector: {selector}"
            await locator.nth(index).set_input_files(str(path))
            return f"Uploaded {path.name} to element {index + 1}/{count} matching selector: {selector}"

    async def run_page_script(self, script_path: str, args_json: str = "{}") -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            path = Path(script_path).expanduser().resolve()
            if not path.is_file():
                return f"Script not found: {path}"
            try:
                args = json.loads(args_json)
            except json.JSONDecodeError as exc:
                return f"Invalid args_json: {exc}"
            result = await self.page.evaluate(path.read_text(encoding="utf-8"), args)
            return json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)

    async def take_screenshot(self, path: Optional[str] = None, full_page: bool = False) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            Path(self.screenshots_dir).mkdir(parents=True, exist_ok=True)
            if not path:
                path = f"step_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            if "/" not in path and "\\" not in path:
                path = str(Path(self.screenshots_dir) / path)
            screenshot = await self.page.screenshot(path=path, full_page=full_page)
            self.last_screenshot_path = path
            mime = "image/png"
            if len(screenshot) > 600_000:
                screenshot = await self.page.screenshot(full_page=full_page, type="jpeg", quality=85)
                mime = "image/jpeg"
            await self.page.wait_for_timeout(1000)
            return f"data:{mime};base64,{base64.b64encode(screenshot).decode('utf-8')}"

    async def wait(self, seconds: float) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            await self.page.wait_for_timeout(int(seconds * 1000))
            return f"Waited {seconds} seconds"

    async def _save_context(self) -> None:
        if self.browser is not None and self.page is not None:
            await self.page.wait_for_timeout(500)

    async def close(self) -> str:
        key = self._bound_session_key()
        if key is not None:
            async with self._tab_lock(key):
                error = await self._release_tab(key)
                return error or "Browser tab closed for this session."
        async with self._operation_state_lock:
            if self._closing:
                wait_for_other_close = True
            else:
                self._closing = True
                self._lifecycle_generation += 1
                self._close_complete.clear()
                wait_for_other_close = False
        if wait_for_other_close:
            await self._close_complete.wait()
            return "Browser closed. Session saved for next time."

        try:
            await self._operations_idle.wait()
            async with self._lifecycle_lock:
                warnings = await self._teardown_unlocked()
        finally:
            async with self._operation_state_lock:
                self._closing = False
                self._close_complete.set()
        if warnings:
            return "Browser closed with cleanup warnings: " + "; ".join(warnings)
        return "Browser closed. Session saved for next time."

    async def _teardown_unlocked(self) -> list[str]:
        """Clear state even when one close operation fails; caller owns lifecycle lock."""
        warnings = []
        interrupted = False
        context, playwright = self.browser, self.playwright
        pages = list(self._pages.values())
        self.browser = None
        self.playwright = None
        self._pages.clear()
        self._page_used.clear()
        self._page_url.clear()
        self._tab_meta.clear()
        self._tab_locks.clear()

        if context is None:
            seen_pages = set()
            for page in pages:
                identity = id(page)
                try:
                    already_closed = page.is_closed()
                except Exception:
                    already_closed = False
                if identity in seen_pages or already_closed:
                    continue
                seen_pages.add(identity)
                try:
                    _, was_cancelled = await _complete_cleanup(
                        asyncio.wait_for(page.close(), timeout=10)
                    )
                    interrupted = interrupted or was_cancelled
                except BaseException as exc:
                    warnings.append(f"close page failed: {exc}")
        if context is not None:
            try:
                _, was_cancelled = await _complete_cleanup(
                    asyncio.wait_for(context.close(), timeout=30)
                )
                interrupted = interrupted or was_cancelled
            except BaseException as exc:
                warnings.append(f"close context failed: {exc}")
        if playwright is not None:
            try:
                _, was_cancelled = await _complete_cleanup(
                    asyncio.wait_for(playwright.stop(), timeout=30)
                )
                interrupted = interrupted or was_cancelled
            except BaseException as exc:
                warnings.append(f"stop playwright failed: {exc}")
        if interrupted:
            raise asyncio.CancelledError
        return warnings

    async def __aenter__(self):
        await self.open_browser()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
