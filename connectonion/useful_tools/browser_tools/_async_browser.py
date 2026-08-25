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

from . import _async_humanize as humanize
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
    if url.startswith(
        ("http://", "https://", "file://", "about:", "data:", "chrome://")
    ):
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


def _age(seconds: float) -> str:
    """Render tab age with the same compact units as BrowserAutomation."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _occupancy_note(meta: Dict[str, Any]) -> str:
    """Describe when a peer-owned tab becomes eligible for reclamation."""
    until = meta.get("needs_until") or 0
    if not until:
        hours, opened_at = meta.get("hours") or 0, meta.get("opened_at")
        if hours > 0 and opened_at:
            until = opened_at.timestamp() + hours * 3600
    if not until:
        return ""

    left = until - time.time()
    when = datetime.fromtimestamp(until).strftime("%H:%M")
    if left > 0:
        return (
            f"owner expects to finish by {when} ({_age(left)} left) — "
            "leave it alone until then"
        )
    return (
        f"owner expected to finish by {when} ({_age(-left)} ago) — "
        "free for another agent to close"
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
        self._session_key = contextvars.ContextVar(
            f"co_browser_session_{suffix}", default=None
        )
        self._operation_depth = contextvars.ContextVar(
            f"co_browser_depth_{suffix}", default=0
        )
        self._lifecycle_lock = asyncio.Lock()
        self._clipboard_lock = asyncio.Lock()
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
                        await page.goto(
                            restore_url, wait_until="domcontentloaded", timeout=30000
                        )
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

    async def open_browser(
        self, headless: Optional[bool] = None, force: bool = False
    ) -> str:
        """Open/reuse the runtime while participating in tab and shutdown admission."""
        if self._operation_depth.get():
            return await self._open_browser(headless=headless, force=force)
        async with self._tab_operation(ensure_page=False):
            return await self._open_browser(headless=headless, force=force)

    async def _open_browser(
        self, headless: Optional[bool] = None, force: bool = False
    ) -> str:
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
                had_previous_state = bool(
                    self.browser or self.playwright or self._pages
                )
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

            await self.page.goto(
                _normalize_url(url), wait_until="domcontentloaded", timeout=30000
            )
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

    async def tab_status(self) -> str:
        """Render registered tabs, including reservations without a live page."""
        async with self._tab_operation(ensure_page=False):
            if not self._tab_meta:
                return "Tabs: none"
            active = self._bound_session_key()
            lines = [f"Tabs ({len(self._tab_meta)}):"]
            for key, meta in list(self._tab_meta.items()):
                page = self._pages.get(key)
                if (
                    page is not None
                    and callable(getattr(page, "is_closed", None))
                    and page.is_closed()
                ):
                    page = None
                where = page.url if page is not None else "(reserved — no page yet)"
                marker = "*" if key == active else " "
                name = "main" if key is None else key
                who = meta.get("who") or "-"
                purpose = meta.get("purpose") or "-"
                line = f"  {marker}[{name}] {where}  who={who}  purpose={purpose!r}"
                opened_at = meta.get("opened_at")
                if opened_at:
                    line += (
                        f"  open {_age((datetime.now() - opened_at).total_seconds())}"
                    )
                last_at = meta.get("last_at")
                if last_at:
                    last_line = (meta.get("last_line") or "")[:60]
                    line += f'\n      last: "{last_line}" · {_age(time.time() - last_at)} ago'
                note = _occupancy_note(meta)
                if note:
                    line += f"\n      {note}"
                lines.append(line)
            return "\n".join(lines)

    async def close_tab(self, key: Optional[str] = None) -> str:
        if key is None:
            key = self._bound_session_key()
        elif key == "main":
            key = None
        async with self._tab_lock(key):
            if key not in self._pages and key not in self._tab_meta:
                return (
                    f"No open tab for {key!r}" if self.browser else "Browser not open"
                )
            error = await self._release_tab(key)
            return error or "Tab closed"

    async def get_current_url(self) -> str:
        async with self._tab_operation():
            return self.page.url if self.page else "Browser not open"

    async def get_system_info(self) -> str:
        system = platform.system()
        if system == "Darwin":
            return (
                "OS: macOS. Use Meta for shortcuts (Meta+a select all, Meta+c copy, "
                "Meta+v paste, Meta+z undo)."
            )
        if system == "Windows":
            return (
                "OS: Windows. Use Control for shortcuts (Control+a select all, "
                "Control+c copy, Control+v paste, Control+z undo)."
            )
        return (
            "OS: Linux. Use Control for shortcuts (Control+a select all, Control+c copy, "
            "Control+v paste, Control+z undo)."
        )

    async def get_text(self) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            return await self.page.locator("body").inner_text()

    async def extract_items_by_selector(
        self,
        container_selector: str,
        text_selector: str,
        max_items: int = 3,
        author_selector: str = "",
        author_attribute: str = "",
        action_selector: str = "",
        action_text: str = "",
        exclude_text_pattern: str = "",
    ) -> str:
        """Extract repeated visible items using caller-provided selectors."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            items = await self.page.evaluate(
                """
                (options) => {
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            rect.width > 0 && rect.height > 0 &&
                            rect.bottom > 0 && rect.top < window.innerHeight;
                    };
                    const textOf = (el) => (el?.innerText || el?.textContent || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/[ \\t]+/g, ' ')
                        .replace(/\\n{3,}/g, '\\n\\n')
                        .trim();
                    const textMatches = (el, expectedText) =>
                        !expectedText || textOf(el) === expectedText;
                    const excludePattern = options.exclude_text_pattern
                        ? new RegExp(options.exclude_text_pattern, 'i') : null;
                    const actions = options.action_selector
                        ? Array.from(document.querySelectorAll(options.action_selector))
                            .filter((action) => isVisible(action) &&
                                textMatches(action, options.action_text))
                        : [];
                    const result = [];
                    const containers = Array.from(
                        document.querySelectorAll(options.container_selector)
                    );
                    for (const container of containers) {
                        const rect = container.getBoundingClientRect();
                        if (rect.bottom <= 0 || rect.top >= window.innerHeight) continue;
                        const containerText = textOf(container);
                        if (excludePattern && excludePattern.test(containerText)) continue;
                        const textNode = container.querySelector(options.text_selector);
                        const text = textOf(textNode);
                        if (!text) continue;
                        let author = '';
                        if (options.author_selector) {
                            const authorNode = container.querySelector(options.author_selector);
                            author = options.author_attribute
                                ? (authorNode?.getAttribute(options.author_attribute) || '').trim()
                                : textOf(authorNode);
                        }
                        const action = actions.find((candidate) =>
                            container.contains(candidate)
                        );
                        result.push({
                            item_index: result.length,
                            author,
                            text,
                            action_index: action ? actions.indexOf(action) : null,
                            has_action: Boolean(action),
                            visible_bounds: {
                                x: Math.round(rect.x), y: Math.round(rect.y),
                                width: Math.round(rect.width), height: Math.round(rect.height)
                            }
                        });
                        if (result.length >= options.max_items) break;
                    }
                    return result;
                }
                """,
                {
                    "container_selector": container_selector,
                    "text_selector": text_selector,
                    "max_items": max_items,
                    "author_selector": author_selector,
                    "author_attribute": author_attribute,
                    "action_selector": action_selector,
                    "action_text": action_text,
                    "exclude_text_pattern": exclude_text_pattern,
                },
            )
            return json.dumps(items or [], indent=2, ensure_ascii=False)

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

    async def click_element_by_selector(
        self,
        selector: str,
        index: int = 0,
        text: str = "",
        frame_url_contains: str = "",
        frame_name: str = "",
    ) -> str:
        """Click a stable selector through humanized pointer input."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"

            if text:
                matches = await self.page.evaluate(
                    """
                    (options) => {
                        const normalize = (el) => (el?.innerText || el?.textContent || '')
                            .replace(/\\u00a0/g, ' ').replace(/[ \\t\\n]+/g, ' ').trim();
                        const isVisible = (el) => {
                            if (!el) return false;
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden' &&
                                rect.width > 0 && rect.height > 0 && rect.bottom > 0 &&
                                rect.top < window.innerHeight;
                        };
                        return Array.from(document.querySelectorAll(options.selector))
                            .filter((el) => isVisible(el) && normalize(el) === options.text)
                            .map((el) => {
                                const rect = el.getBoundingClientRect();
                                return {x: rect.x + rect.width / 2, y: rect.y + rect.height / 2};
                            });
                    }
                    """,
                    {"selector": selector, "text": text},
                )
                count = len(matches)
                if count == 0:
                    return f"No visible element found for selector: {selector} with text: {text}"
                if index < 0 or index >= count:
                    return f"Selector matched {count} elements with text {text!r}; index {index} is out of range"
                await humanize.click(
                    self.page, matches[index]["x"], matches[index]["y"]
                )
                await self._save_context()
                await self.page.wait_for_timeout(1000)
                return f"Clicked element {index + 1}/{count} matching selector: {selector} with text: {text}"

            if frame_url_contains or frame_name:
                candidates = []
                for frame in self.page.frames:
                    url = getattr(frame, "url", "") or ""
                    name = getattr(frame, "name", "") or ""
                    if callable(name):
                        name = name()
                    if frame_url_contains and frame_url_contains not in url:
                        continue
                    if frame_name and frame_name != name:
                        continue
                    locator = frame.locator(selector)
                    candidates.extend(
                        locator.nth(i) for i in range(await locator.count())
                    )
                where = f" in frames matching {(frame_url_contains or frame_name)!r}"
            else:
                locator = self.page.locator(selector)
                candidates = [locator.nth(i) for i in range(await locator.count())]
                where = ""

            count = len(candidates)
            if count == 0:
                return f"No element found for selector: {selector}{where}"
            if index < 0 or index >= count:
                return f"Selector matched {count} elements{where}; index {index} is out of range"
            target = candidates[index]
            box = await target.bounding_box()
            if box:
                await humanize.click(self.page, 0, 0, box=box)
            else:
                await target.click(force=True)
            await self._save_context()
            await self.page.wait_for_timeout(1000)
            return f"Clicked element {index + 1}/{count} matching selector: {selector}{where}"

    async def type_text_by_selector(
        self, selector: str, text: str, index: int = 0
    ) -> str:
        """Focus a stable selector and type through async humanized input."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            locator = self.page.locator(selector)
            count = await locator.count()
            if count == 0:
                return f"No element found for selector: {selector}"
            if index < 0 or index >= count:
                return (
                    f"Selector matched {count} elements; index {index} is out of range"
                )
            await locator.nth(index).click(force=True)
            await humanize.type_text(self.page, text, self._clipboard_lock)
            await self.page.wait_for_timeout(1000)
            return f"Typed text into element {index + 1}/{count} matching selector: {selector}"

    async def mouse_click(self, x: int, y: int) -> str:
        """Humanize an exact coordinate click without blocking the event loop."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            await humanize.click(self.page, x, y)
            await asyncio.sleep(1)
            return f"Clicked at ({x}, {y})"

    async def click_element_near_selector(
        self,
        anchor_selector: str,
        target_selector: str,
        target_text: str = "",
        anchor_index: int = -1,
        container_selector: str = "",
        require_anchor_text: bool = False,
        wait_ms: int = 1000,
        verify_anchor_text_cleared: bool = False,
    ) -> str:
        """Click the nearest visible target below a stable visible anchor."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            target = await self.page.evaluate(
                """
                (options) => {
                    const normalize = (el) => (el?.innerText || el?.textContent || '')
                        .replace(/\\u00a0/g, ' ').replace(/[ \\t\\n]+/g, ' ').trim();
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' &&
                            rect.width > 0 && rect.height > 0 && rect.bottom > 0 &&
                            rect.top < window.innerHeight;
                    };
                    const isEnabled = (button) =>
                        !button.disabled && button.getAttribute('aria-disabled') !== 'true';
                    const textMatches = (el) => !options.target_text || normalize(el) === options.target_text;
                    const anchors = Array.from(document.querySelectorAll(options.anchor_selector))
                        .filter((anchor) => isVisible(anchor))
                        .filter((anchor) => !options.require_anchor_text || normalize(anchor).length > 0);
                    if (!anchors.length) {
                        return {ok: false, error: `No visible anchor found for selector: ${options.anchor_selector}`};
                    }
                    let anchorIndex = options.anchor_index;
                    if (anchorIndex < 0) anchorIndex = anchors.length + anchorIndex;
                    if (anchorIndex < 0 || anchorIndex >= anchors.length) {
                        return {ok: false, error: `Anchor selector matched ${anchors.length} elements; index ${options.anchor_index} is out of range`};
                    }
                    const anchor = anchors[anchorIndex];
                    const anchorRect = anchor.getBoundingClientRect();
                    let container = options.container_selector ? anchor.closest(options.container_selector) : null;
                    container = container || anchor.closest('form') || anchor.parentElement || document.body;
                    const targets = Array.from(container.querySelectorAll(options.target_selector))
                        .filter((candidate) => isVisible(candidate) && isEnabled(candidate) && textMatches(candidate));
                    let target = targets
                        .map((candidate) => ({candidate, rect: candidate.getBoundingClientRect()}))
                        .filter(({rect}) => rect.top >= anchorRect.top - 8)
                        .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left)[0]?.candidate;
                    if (!target) {
                        target = Array.from(document.querySelectorAll(options.target_selector))
                            .filter((candidate) => isVisible(candidate) && isEnabled(candidate) && textMatches(candidate))
                            .map((candidate) => ({candidate, rect: candidate.getBoundingClientRect()}))
                            .filter(({rect}) => rect.top >= anchorRect.top - 8)
                            .sort((a, b) => Math.abs(a.rect.top - anchorRect.top) -
                                Math.abs(b.rect.top - anchorRect.top) || a.rect.left - b.rect.left)[0]?.candidate;
                    }
                    if (!target) {
                        return {ok: false, error: `No visible enabled target found near anchor for selector: ${options.target_selector}`, anchor_text: normalize(anchor)};
                    }
                    const rect = target.getBoundingClientRect();
                    return {ok: true, x: rect.x + rect.width / 2, y: rect.y + rect.height / 2,
                        anchor_text: normalize(anchor), target_text: normalize(target)};
                }
                """,
                {
                    "anchor_selector": anchor_selector,
                    "target_selector": target_selector,
                    "target_text": target_text,
                    "anchor_index": anchor_index,
                    "container_selector": container_selector,
                    "require_anchor_text": require_anchor_text,
                },
            )
            if not target or not target.get("ok"):
                return (
                    target.get("error", "Could not find target near anchor")
                    if target
                    else "Could not find target near anchor"
                )
            await humanize.click(self.page, target["x"], target["y"])
            await self.page.wait_for_timeout(wait_ms)
            await self._save_context()
            state = "clicked"
            if verify_anchor_text_cleared:
                state = await self.page.evaluate(
                    """
                    (options) => {
                        const normalize = (el) => (el?.innerText || el?.textContent || '')
                            .replace(/\\u00a0/g, ' ').replace(/[ \\t\\n]+/g, ' ').trim();
                        const isVisible = (el) => {
                            if (!el) return false;
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            return style.display !== 'none' && style.visibility !== 'hidden' &&
                                rect.width > 0 && rect.height > 0 && rect.bottom > 0 &&
                                rect.top < window.innerHeight;
                        };
                        const matchingAnchor = Array.from(document.querySelectorAll(options.anchor_selector))
                            .find((anchor) => isVisible(anchor) && normalize(anchor) === options.anchor_text);
                        return matchingAnchor ? 'uncertain_anchor_still_contains_text' : 'anchor_text_cleared';
                    }
                    """,
                    {
                        "anchor_selector": anchor_selector,
                        "anchor_text": target["anchor_text"],
                    },
                )
            return (
                "Clicked target near anchor; "
                f"state={state}; anchor_text={target['anchor_text']!r}; "
                f"target_text={target['target_text']!r}"
            )

    async def count_elements_by_selector(self, selector: str) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            count = await self.page.locator(selector).count()
            return (
                f"{count} element{'s' if count != 1 else ''} match selector: {selector}"
            )

    async def get_element_text_by_selector(self, selector: str, index: int = 0) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            locator = self.page.locator(selector)
            count = await locator.count()
            if count == 0:
                return f"No element found for selector: {selector}"
            if index < 0 or index >= count:
                return (
                    f"Selector matched {count} elements; index {index} is out of range"
                )
            return await locator.nth(index).inner_text()

    async def fill_text_by_selector(
        self, selector: str, text: str, index: int = 0
    ) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            locator = self.page.locator(selector)
            count = await locator.count()
            if count == 0:
                return f"No element found for selector: {selector}"
            if index < 0 or index >= count:
                return (
                    f"Selector matched {count} elements; index {index} is out of range"
                )
            await locator.nth(index).fill(text)
            await self.page.wait_for_timeout(1000)
            return f"Filled element {index + 1}/{count} matching selector: {selector}"

    async def upload_file_by_selector(
        self,
        selector: str,
        file_path: str,
        index: int = 0,
        frame_url_contains: str = "",
        frame_name: str = "",
    ) -> str:
        """Upload a local file into a frame-aware file-input selector."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            path = self._local_path(file_path)
            if not path.exists():
                return f"File not found: {path}"
            if not path.is_file():
                return f"Path is not a file: {path}"

            matches = []
            for frame_index, frame, name, url in self._matching_frames(
                frame_url_contains,
                frame_name,
            ):
                locator = frame.locator(selector)
                count = await locator.count()
                for locator_index in range(count):
                    matches.append((frame_index, name, url, locator.nth(locator_index)))

            if not matches:
                return f"No file input found for selector: {selector}"
            if index < 0 or index >= len(matches):
                return (
                    f"Selector matched {len(matches)} file input(s); "
                    f"index {index} is out of range"
                )

            frame_index, name, url, target = matches[index]
            await target.set_input_files(str(path))
            await self.page.wait_for_timeout(1500)
            await self._save_context()
            return json.dumps(
                {
                    "ok": True,
                    "uploaded": True,
                    "file": str(path),
                    "selector": selector,
                    "index": index,
                    "frame": {"index": frame_index, "name": name, "url": url},
                },
                indent=2,
                ensure_ascii=False,
            )

    async def upload_file_after_click_by_selector(
        self,
        click_selector: str,
        file_path: str,
        index: int = 0,
        text: str = "",
        frame_url_contains: str = "",
        frame_name: str = "",
        timeout_ms: int = 5000,
    ) -> str:
        """Click a frame-aware upload control and handle its file chooser."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            path = self._local_path(file_path)
            if not path.exists():
                return f"File not found: {path}"
            if not path.is_file():
                return f"Path is not a file: {path}"

            matches = []
            for frame_index, frame, name, url in self._matching_frames(
                frame_url_contains,
                frame_name,
            ):
                locator = frame.locator(click_selector)
                count = await locator.count()
                for locator_index in range(count):
                    target = locator.nth(locator_index)
                    if text:
                        try:
                            candidate_text = (
                                (await target.inner_text())
                                .replace("\u00a0", " ")
                                .strip()
                            )
                        except Exception:
                            candidate_text = ""
                        if candidate_text != text:
                            continue
                    matches.append((frame_index, name, url, target))

            if not matches:
                suffix = f" with text: {text}" if text else ""
                return (
                    f"No upload trigger found for selector: "
                    f"{click_selector}{suffix}"
                )
            if index < 0 or index >= len(matches):
                return (
                    f"Selector matched {len(matches)} upload trigger(s); "
                    f"index {index} is out of range"
                )

            frame_index, name, url, target = matches[index]
            async with self.page.expect_file_chooser(
                timeout=timeout_ms
            ) as chooser_info:
                await target.click(force=True)
            chooser = await chooser_info.value
            await chooser.set_files(str(path))
            await self.page.wait_for_timeout(2500)
            await self._save_context()
            return json.dumps(
                {
                    "ok": True,
                    "uploaded": True,
                    "file": str(path),
                    "click_selector": click_selector,
                    "text": text,
                    "index": index,
                    "frame": {"index": frame_index, "name": name, "url": url},
                },
                indent=2,
                ensure_ascii=False,
            )

    @staticmethod
    def _local_path(value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else Path.cwd() / path

    def _matching_frames(
        self,
        frame_url_contains: str = "",
        frame_name: str = "",
    ):
        for frame_index, frame in enumerate(self.page.frames):
            url = getattr(frame, "url", "") or ""
            raw_name = getattr(frame, "name", "") or ""
            name = raw_name() if callable(raw_name) else raw_name
            if frame_url_contains and frame_url_contains not in url:
                continue
            if frame_name and frame_name != name:
                continue
            yield frame_index, frame, name, url

    def _load_script_args(
        self,
        script_path: str,
        args_json: str,
    ) -> tuple[Optional[str], Optional[dict], Optional[str]]:
        path = self._local_path(script_path)
        if not path.exists():
            return None, None, f"Script not found: {path}"
        if not path.is_file():
            return None, None, f"Script path is not a file: {path}"
        try:
            args = json.loads(args_json or "{}")
        except json.JSONDecodeError as exc:
            return None, None, f"Invalid args_json: {exc}"
        return path.read_text(encoding="utf-8"), args, None

    async def run_page_script(self, script_path: str, args_json: str = "{}") -> str:
        """Run a local JavaScript file in the main page and return JSON."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            script, args, error = self._load_script_args(script_path, args_json)
            if error:
                return error
            result = await self.page.evaluate(script, args)
            return json.dumps(result, indent=2, ensure_ascii=False)

    async def run_frame_script(
        self,
        script_path: str,
        args_json: str = "{}",
        frame_url_contains: str = "",
        frame_name: str = "",
        first_ok: bool = True,
    ) -> str:
        """Run a local JavaScript file in matching frames and return JSON."""
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            script, args, error = self._load_script_args(script_path, args_json)
            if error:
                return error

            frames = []
            matched = None
            for frame_index, frame, name, url in self._matching_frames(
                frame_url_contains,
                frame_name,
            ):
                frame_info = {
                    "index": frame_index,
                    "name": name,
                    "url": url,
                    "ok": False,
                    "result": None,
                    "error": None,
                }
                try:
                    result = await frame.evaluate(script, args)
                    frame_info["result"] = result
                    frame_info["ok"] = bool(
                        isinstance(result, dict) and result.get("ok") is True
                    )
                except Exception as exc:
                    frame_info["error"] = str(exc)
                frames.append(frame_info)
                if frame_info["ok"] and matched is None:
                    matched = frame_info
                    if first_ok:
                        break

            response = {
                "ok": matched is not None,
                "matched_frame": matched,
                "frames": frames,
            }
            if not frames:
                response["reason"] = "no frames matched filters"
            elif matched is None:
                response["reason"] = "no frame returned ok: true"
            return json.dumps(response, indent=2, ensure_ascii=False)

    async def take_screenshot(
        self, path: Optional[str] = None, full_page: bool = False
    ) -> str:
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
                screenshot = await self.page.screenshot(
                    full_page=full_page, type="jpeg", quality=85
                )
                mime = "image/jpeg"
            await self.page.wait_for_timeout(1000)
            return f"data:{mime};base64,{base64.b64encode(screenshot).decode('utf-8')}"

    async def set_viewport(self, width: int, height: int) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            await self.page.set_viewport_size({"width": width, "height": height})
            return f"Viewport set to {width}x{height}"

    async def wait_for_text(self, text: str, timeout: int = 30) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            await self.page.wait_for_selector(f"text='{text}'", timeout=timeout * 1000)
            return f"Found text: '{text}'"

    async def wait(self, seconds: float) -> str:
        async with self._tab_operation():
            if self.page is None:
                return "Browser not open"
            await self.page.wait_for_timeout(int(seconds * 1000))
            return f"Waited for {seconds} seconds"

    async def extract_data(self, selector: str) -> list[str]:
        async with self._tab_operation():
            if self.page is None:
                return []
            elements = self.page.locator(selector)
            count = await elements.count()
            return [await elements.nth(index).inner_text() for index in range(count)]

    async def get_links_from_page(self, domain_filter: str = "") -> list[str]:
        async with self._tab_operation():
            if self.page is None:
                return []
            urls = await self.page.evaluate(
                """
                (filter) => {
                    const seen = new Set();
                    const result = [];
                    for (const a of document.querySelectorAll('a[href]')) {
                        const href = a.href;
                        if (href && !seen.has(href) && (!filter || href.includes(filter))) {
                            seen.add(href);
                            result.push(href);
                        }
                    }
                    return result;
                }
                """,
                domain_filter,
            )
            return urls or []

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
