"""
Purpose: Natural language browser automation via Patchright (a stealth-patched, API-compatible Playwright fork) with persistent profile and auto-save
LLM-Note:
  Dependencies: imports from [patchright.sync_api, connectonion Agent/llm_do, cli/browser_agent/element_finder, pydantic, pathlib, dotenv] | imported by [cli/commands/browser_commands.py] | tested by [tests/e2e/cli/test_browser_agent.py]
  Data flow: BrowserAutomation() initializes Playwright → opens browser with persistent context → provides tools (navigate, find_element, click, type_text, screenshot, scroll, wait_for_login) → auto-saves cookies after each critical action → Agent uses these tools via natural language → element_finder.py uses vision LLM to locate elements | screenshots saved to .tmp/ directory
  State/Effects: maintains browser/page/context state | persistent profile at ~/.co/browser_profile/ | auto-saves cookies after navigation and manual login | writes screenshots to .tmp/{timestamp}.png | modifies form_data dict for form fills | context manager ensures cleanup | all public methods dispatch to one dedicated browser thread (Playwright sync API is thread-bound), so a shared instance is safe to call from any thread
  Integration: exposes BrowserAutomation(use_chrome_profile, headless) with methods: navigate(url), find_element(description), screenshot(viewport), scroll(direction, description), click(description), keyboard_type(text), keyboard_press(key), wait_for_login(seconds) | used by `co browser` CLI command
  Performance: headless by default (faster) | persistent context (instant profile load) | vision model for element finding (slower but accurate) | screenshots base64-encoded for LLM analysis | auto-save adds 500ms delay after critical actions
  Errors: returns error string if Playwright not installed | returns "Browser already open" if live browser exists | element not found returns descriptive error
Browser Agent for CLI - Natural language browser automation.

This module provides a browser automation agent that understands natural language
requests for browser operations via the ConnectOnion CLI.

Features:
- Persistent profile with crash-resistant auto-save (cookies saved after every navigation and login)
- AI-powered element finding using natural language
- Form interaction: find elements, type text, click buttons
- Screenshot with viewport presets
- Universal scroll with AI strategy selection
- Manual login pause for 2FA/CAPTCHA
"""

import os
import base64
import functools
import inspect
import json
import platform
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from connectonion import Agent, llm_do
from connectonion.useful_plugins import image_result_formatter, ui_stream
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from . import element_finder
from .browser_config import CHROME_DEFAULT_ARGS, IGNORE_DEFAULT_ARGS

# Default screenshots directory
SCREENSHOTS_DIR = Path.cwd() / ".tmp"

# Patchright is a stealth-patched, API-compatible drop-in for Playwright. It removes
# driver-level automation tells (the Runtime.enable / Console.enable CDP leaks and the
# navigator.webdriver flag) that Chrome launch flags and page init scripts cannot reach,
# so it fixes anti-detection below where our old flag stack operated. The sync API is
# identical, so only the import line changes; sync_playwright keeps its name because that
# is exactly what patchright.sync_api exports.
try:
    from patchright.sync_api import sync_playwright, Page, Browser, Playwright
    BROWSER_AVAILABLE = True
except ImportError:
    BROWSER_AVAILABLE = False

# Path to the browser agent system prompt


def _no_auto_tab(method):
    """Mark a method so the dispatch wrapper does NOT auto-create a tab for it.

    Most public methods work on the current session's tab, so the wrapper makes
    sure one exists before they run. The marked methods manage tabs themselves:
    open_browser creates the tab after launching the context; close/save_state
    operate on the whole context, and auto-creating a fresh tab right before
    them is wrong (close would restore a reclaimed tab just to close it again).

    A marker on the method instead of a name set: it sits next to the code it
    exempts, and renaming the method can't silently break the match.
    """
    method._no_auto_tab = True
    return method


# Playwright's sync API binds to the thread that started it and raises
# "Cannot switch to a different thread" from any other. Servers like host()
# run each agent turn on an arbitrary threadpool thread, so consecutive turns
# crash the shared browser. Route every public method through the instance's
# dedicated worker thread: playwright starts there and every call lands there.
#
# The wrapper also routes per session: it reads the caller thread's session key
# (set by the bind_browser_session plugin via _bind_session), propagates it onto
# the worker thread, and ensures that session's own tab exists before the method
# runs (so self.page resolves to the right tab).
def _runs_on_browser_thread(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        key = self._bound_session_key()  # read on the caller (agent) thread

        def run():
            self._session_binding.key = key   # propagate onto the worker thread
            if not getattr(method, "_no_auto_tab", False):
                self._ensure_page(key)        # this session gets / keeps its own tab
            return method(self, *args, **kwargs)

        if threading.current_thread() is self._executor_thread:
            return run()
        return self._executor.submit(run).result()

    return wrapper


def _public_methods_run_on_browser_thread(cls):
    for name, method in vars(cls).copy().items():
        if not name.startswith("_") and inspect.isfunction(method):
            setattr(cls, name, _runs_on_browser_thread(method))
    return cls


def _browser_proxy_from_env():
    """Build Playwright's proxy config from the BROWSER_PROXY env var, or None if unset.

    BROWSER_PROXY routes the browser's traffic through an HTTP or SOCKS proxy — e.g. to
    control the egress IP, test geo-specific behaviour, or comply with a corporate
    network policy. Formats:
        socks5://host:port              (no auth; Chromium ignores SOCKS auth)
        http://user:pass@host:port      (HTTP proxy with auth)
    Use only against sites whose terms permit it. Unset => None => no proxy, current
    behaviour unchanged.
    """
    url = os.environ.get("BROWSER_PROXY", "").strip()
    if not url:
        return None
    p = urllib.parse.urlparse(url)
    server = f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")
    proxy = {"server": server}
    if p.username:
        proxy["username"] = urllib.parse.unquote(p.username)
    if p.password:
        proxy["password"] = urllib.parse.unquote(p.password)
    return proxy


def _pid_alive(pid: int) -> bool:
    """True if a process with this pid exists (signal 0 probes it without touching it)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but owned by another user
    return True


def _clear_stale_singleton_lock(profile_dir: Path) -> None:
    """Remove Chrome's Singleton* lock artifacts if the process that held them is gone.

    An uncleanly-killed Chrome (daemon SIGKILL, crash, OOM) leaves a SingletonLock symlink
    pointing at "<host>-<pid>" in the profile. On the next launch Chrome sees it and refuses
    to start ("profile appears to be in use"), bricking the persistent login profile until it
    is cleared by hand — which is why ~/.co accumulates *.recover_quarantine backups. Chrome
    self-heals this only sometimes (same host, dead pid) and fails across hostname changes or
    pid reuse, so we clear it ourselves.

    Only clear when the owning pid is dead: a live Chrome legitimately owns the lock. These are
    lock artifacts, not login data (cookies live elsewhere in the profile), so removing a dead
    lock is safe.
    """
    lock = profile_dir / "SingletonLock"
    if not lock.is_symlink():
        return
    tail = os.readlink(lock).rsplit("-", 1)[-1]
    if not tail.isdigit():
        return  # unrecognized lock format — don't guess, leave it alone
    if _pid_alive(int(tail)):
        return  # a live Chrome owns it
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        (profile_dir / name).unlink(missing_ok=True)


def driver_stealth_status():
    """Report whether the installed Patchright driver still has its stealth patches.

    Patchright ships its anti-detection patches in a separately-downloaded driver that has
    silently regressed to the unpatched vanilla Playwright build across releases — leaving
    navigator.webdriver=true and the "controlled by automated test software" infobar. The
    patched driver always injects `--disable-blink-features=AutomationControlled`; the vanilla
    one never does, so scanning the driver for that literal is a fast integrity check that
    needs no browser launch. Surfaced by `co browser status` and `co doctor`.

    Returns (status, version, detail) where status is 'ok' | 'broken' | 'missing'.
    """
    import importlib.util
    import importlib.metadata

    if importlib.util.find_spec("patchright") is None:
        return "missing", "", "patchright not installed — pip install patchright && patchright install chrome"

    import patchright
    version = importlib.metadata.version("patchright")
    lib = Path(patchright.__file__).parent / "driver" / "package" / "lib"
    marker = "disable-blink-features=AutomationControlled"
    patched = any(marker in p.read_text(errors="ignore") for p in lib.rglob("*.js"))
    if patched:
        return "ok", version, "stealth patches present"
    return ("broken", version,
            "UNPATCHED driver — navigator.webdriver leaks. "
            "Fix: pip install --force-reinstall --no-cache-dir patchright")


def _occupancy_help(verb: str, url: str) -> str:
    """Message shown to the AI AGENT (not a human) when it uses a tab with no purpose.
    It must generate the values from the user's request and re-run."""
    return (
        "This tab has no purpose yet — say why you're using it. "
        "(This message is for the AI agent, not the user.)\n"
        "\n"
        "Re-run and fill these in from what the user asked you to do:\n"
        f'  co browser {verb} {url} --purpose="<why you\'re opening this tab>" '
        '--who="<the user this is for>" --hours=<how long you\'ll need it>\n'
        "\n"
        "- --purpose: generate it from the user's request — the reason you're on this page.\n"
        "- --who: tag the user you're doing this for.\n"
        "- --hours: estimate how long you'll hold this tab (e.g. 2, 3, 10). Informational only —\n"
        "  after it elapses, `co browser status` flags the tab \"may be closed\"; it is NOT closed for you.\n"
        "- When the task is done, close it yourself:  co browser closetab <id>\n"
        "- First run `co browser status` — reuse an open tab instead of opening a new one."
    )


def _age(seconds: float) -> str:
    """Compact age string for how long a tab has been open: Xs / Xm / Xh / Xd."""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


@_public_methods_run_on_browser_thread
class BrowserAutomation:
    """Browser automation with natural language support.

    Simple interface for complex web interactions.
    Auto-initializes browser on creation for immediate use.
    Persistent profile with crash-resistant auto-save.

    Cookies and storage automatically save after:
    - Every navigation (go_to)
    - Manual login confirmation (wait_for_manual_login)
    - Browser close

    This ensures session persistence even if the process crashes.
    """

    def __init__(self, use_chrome_profile: bool = True, headless: bool = False, seed_state: Optional[str] = None,
                 tab_idle_ttl: float = 3600.0, max_tabs: int = 10):
        """Initialize browser automation.

        Args:
            use_chrome_profile: If True, uses your Chrome cookies/sessions.
                               Chrome must be closed before running.
            headless: If True, browser runs without visible window (default True).
            seed_state: Optional path to a Playwright storage_state JSON (a {"cookies": [...]}
                        file produced by save_state on another machine). When set, those cookies
                        are injected into the context once, right after it is created and before
                        any navigation, so a deployed agent starts already signed in. Cookies are
                        applied with add_cookies because launch_persistent_context() cannot accept
                        storage_state=. The file holds live session cookies — inject it from the
                        deploy secret store and never commit it. Unset => no injection, current
                        behaviour unchanged.
            tab_idle_ttl: Seconds a session's tab may sit idle before being reclaimed
                          (the session transparently gets a fresh tab restored to its
                          last URL on next use). Lower it on memory-tight deploy boxes.
            max_tabs: Hard cap on concurrent session tabs; beyond it the
                      least-recently-used tabs are reclaimed first.
        """
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        # One tab per session (chat panel) in the shared context, so concurrent
        # sessions don't navigate over each other. Key = session_id (None = no
        # session bound = single shared tab, the original single-page behaviour).
        # The binding is per (instance, thread): _bind_session records on the
        # caller thread which session its calls belong to, and the dispatch
        # wrapper carries that key onto the worker thread.
        self._session_binding = threading.local()
        self._pages: Dict[Optional[str], "Page"] = {}
        self._page_used: Dict[Optional[str], float] = {}   # key -> last-use monotonic ts (LRU/TTL)
        self._page_url: Dict[Optional[str], str] = {}      # key -> last url (restore a reclaimed tab)
        self._tab_meta: Dict[Optional[str], Dict[str, Any]] = {}  # key -> {who, purpose, hours, opened_at}
        self._tab_idle_ttl = tab_idle_ttl
        self._max_tabs = max_tabs
        self._max_url_memory = 200    # bound the restore-url map; session ids are unique per panel
        self.current_url: str = ""
        self.form_data: Dict[str, Any] = {}
        self.use_chrome_profile = use_chrome_profile
        self._screenshots = []
        self._headless = headless
        self._seed_state = seed_state
        self._seeded = False
        self.screenshots_dir = str(SCREENSHOTS_DIR)
        self.last_screenshot_path = None  # file path of the most recent screenshot
        # All public methods run on this one thread (see _public_methods_run_on_browser_thread).
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="browser")
        self._executor_thread = self._executor.submit(threading.current_thread).result()

    def _browser_is_usable(self) -> bool:
        """Return True when the current Playwright page can still be operated."""
        key = self._bound_session_key()

        def run():
            self._session_binding.key = key
            return self._browser_is_usable_on_browser_thread()

        if threading.current_thread() is self._executor_thread:
            return run()
        return self._executor.submit(run).result()

    def _browser_is_usable_on_browser_thread(self) -> bool:
        """Check browser usability on Playwright's owning thread."""
        if not self.browser or not self.page:
            return False

        try:
            is_closed = getattr(self.page, "is_closed", None)
            if callable(is_closed) and is_closed():
                return False
            _ = self.page.url
            return True
        except Exception:
            return False

    def _context_is_alive(self) -> bool:
        """True when the shared browser CONTEXT is up — independent of which session
        is currently bound. The daemon's serve-loop liveness check must use this, not
        _browser_is_usable(): the latter reads the bound session's page, so a command
        on a registered-but-page-less tab would read False and wrongly tear the whole
        browser down for every other session."""
        if not self.browser:
            return False

        def run():
            try:
                pages = list(self.browser.pages)
            except Exception:
                return False
            for pg in pages:
                is_closed = getattr(pg, "is_closed", None)
                if not (callable(is_closed) and is_closed()):
                    return True
            # A live context with zero open pages is still usable (a page opens on demand).
            return True

        if threading.current_thread() is self._executor_thread:
            return run()
        return self._executor.submit(run).result()

    def _launch_failed(self) -> bool:
        """True when a launch started Playwright but no browser context came up.

        open_browser() starts Playwright, then opens the persistent context; if that
        launch raises (e.g. Chrome aborts at startup), self.playwright stays set while
        self.browser is None. The daemon reads this to exit instead of lingering as a
        permanently-broken zombie that still owns the socket. Plain attribute reads, so
        it is safe to call from any thread without routing to the browser worker."""
        return self.playwright is not None and self.browser is None

    @property
    def page(self):
        """The Playwright tab for the session this call belongs to.

        Each session (chat panel) gets its own tab in the shared, single-login
        context, so concurrent sessions don't navigate over each other. The session
        key is set by the bind_browser_session plugin on the agent thread and
        propagated onto the worker thread by the dispatch decorator; both threads
        read it from this instance's threading.local. Returns None until the tab is
        created (so the existing `if not self.page: ...` guards still read "browser
        not open").
        """
        return self._pages.get(self._bound_session_key())

    @page.setter
    def page(self, value):
        """Set the current session's tab. Internal flows create tabs via
        _ensure_page; this setter keeps `self.page = <page>` working for callers
        and tests that inject a page directly (it writes the current session's slot)."""
        key = self._bound_session_key()
        self._pages[key] = value
        self._page_used[key] = time.monotonic()

    def _bound_session_key(self):
        """The session key bound to the current thread, or None for an unscoped
        caller (single-session CLI, tests) — None means the single shared tab."""
        return getattr(self._session_binding, "key", None)

    def _bind_session(self, session_id) -> None:
        """Record, on the CALLER (agent) thread, which session the next browser
        calls on this thread belong to. Underscore-prefixed so it is neither
        dispatched to the worker thread nor exposed to the LLM as a tool; the
        bind_browser_session plugin calls it before each tool, and the dispatch
        decorator reads the binding to route to the right tab."""
        self._session_binding.key = session_id

    def _ensure_page(self, key) -> None:
        """Make sure session `key` has a live tab, then reclaim abandoned ones.

        Reused by two callers, always on the worker thread: the dispatch decorator
        (before every tab-using tool, so self.page resolves to this session's tab)
        and open_browser (to create the first tab after launching the context).

        Creates the tab in the shared context (restored to its last URL), stamps its
        last-use time, then reclaims. No-op until the context is open; harmless if the
        tab already exists.

        Reclaim bounds memory but never closes the active `key`: first tabs idle past
        _tab_idle_ttl (a panel untouched for an hour), then — only if still over
        _max_tabs — the least-recently-used ones as a runaway backstop. A reclaimed
        session transparently gets a fresh restored tab next call (no "target closed").
        """
        if not self.browser:
            return

        page = self._pages.get(key)
        if page is None or (callable(getattr(page, "is_closed", None)) and page.is_closed()):
            page = self.browser.new_page()
            page.set_default_navigation_timeout(60000)
            page.set_viewport_size({"width": 1920, "height": 1200})
            # No navigator.webdriver init script: Patchright hides it at the driver level,
            # and add_init_script injection is itself a timing-detectable tell.
            restore_url = self._page_url.get(key)
            if restore_url:  # a reclaimed session comes back to where it was
                try:
                    page.goto(restore_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
            self._pages[key] = page
        self._page_used[key] = time.monotonic()

        now = time.monotonic()
        for k in [k for k, t in list(self._page_used.items())
                  if k != key and now - t > self._tab_idle_ttl]:
            self._close_tab(k, forget=False)
        if len(self._pages) > self._max_tabs:
            lru_first = sorted(
                (k for k in self._pages if k != key),
                key=lambda k: self._page_used.get(k, 0.0),
            )
            for k in lru_first[: len(self._pages) - self._max_tabs]:
                self._close_tab(k, forget=False)

    def _close_tab(self, key, forget: bool = True) -> Optional[str]:
        """Close one session's tab, remembering its URL so the session can resume.

        Reused by two callers: _ensure_page's reclaim (best-effort, ignores the
        return) and close() (surfaces the return as a cleanup warning). Returns an
        error string if the page would not close, else None.

        forget=False (the reclaim path) keeps the tab's _tab_meta registration:
        a reclaimed tab must transparently resume — same owner, same purpose —
        when its next command recreates the page."""
        page = self._pages.pop(key, None)
        self._page_used.pop(key, None)
        if forget:
            self._tab_meta.pop(key, None)
        if page is None:
            return None
        try:
            url = page.url
        except Exception:
            url = None
        if url:
            # Remember where the session was so it resumes there, but bound the map:
            # session ids are unique per panel, so without a cap it grows forever on a
            # long-lived shared host. Re-insert (LRU) then trim the oldest keys.
            self._page_url.pop(key, None)
            self._page_url[key] = url
            while len(self._page_url) > self._max_url_memory:
                self._page_url.pop(next(iter(self._page_url)))
        try:
            page.close()
        except Exception as exc:
            return f"close page failed: {exc}"
        return None

    @_no_auto_tab
    def open_browser(self, headless: bool = None, force: bool = False) -> str:
        """Open a new browser window.

        Args:
            headless: If True, browser runs without visible window. Defaults to the value set in __init__.
            force: If True, close the current browser first and open a fresh context.

        Note: If use_chrome_profile=True, Chrome must be completely closed.
        """
        if headless is None:
            headless = self._headless
        if not BROWSER_AVAILABLE:
            return "Browser tools not installed. Run: pip install patchright && patchright install chrome"

        # If a shared context is already running, a brand-new session has no tab in it yet.
        # Give this session its tab BEFORE judging usability, so a new session never reads
        # the shared context as "unusable" (its own page is None) and tears it down — that
        # would close the tabs other sessions are actively using. If the context is really
        # dead, _ensure_page can't make a tab and the check below falls through to relaunch.
        if self.browser is not None:
            try:
                self._ensure_page(self._bound_session_key())
            except Exception:
                pass

        if self._browser_is_usable():
            if not force:
                return "<system-reminder>Browser already open and usable. Continue using the current browser page.</system-reminder>"
            # force=True: caller wants a fresh start. A bound session (hosted multi-session)
            # recycles only its OWN tab — a full teardown would kill every other session's
            # tabs. An unbound caller (single-session CLI) tears the whole context down.
            key = self._bound_session_key()
            if key is not None:
                self._close_tab(key, forget=False)   # same session continues — keep its registration
                self._page_url.pop(key, None)   # fresh = a blank tab, not the old url restored
                self._ensure_page(key)
                return "Opened a fresh tab for this session."
            self._teardown()
            had_previous_browser_state = True
        else:
            had_previous_browser_state = bool(self.browser or self.page or self.playwright)
            if had_previous_browser_state:
                self._teardown()   # context is dead/unusable — full cleanup before relaunch

        self.playwright = sync_playwright().start()

        # Dedicated persistent profile owned by co
        # First run: fresh profile, user logs in once. All later runs reuse saved cookies.
        profile_dir = Path.home() / ".co" / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        # A previous Chrome that died uncleanly can leave a SingletonLock that blocks this
        # launch. Clear it if its owner is dead, so the persistent profile can't get bricked.
        _clear_stale_singleton_lock(profile_dir)

        # Remove --no-sandbox from args since Playwright adds it by default
        # Just keep the flags we actually need
        # NOTE: --use-mock-keychain removed to fix cookie persistence on macOS
        # See: https://github.com/microsoft/playwright/issues/31736
        # Can test removing this in the future if cookie issues persist

        # Use Google Chrome instead of Chromium when it exists.
        chrome_paths = {
            "Darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
            "Linux": ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/opt/google/chrome/chrome"],
            "Windows": [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
        }.get(platform.system(), [])
        chrome_path = next((p for p in chrome_paths if os.path.exists(p)), None)

        # Session persistence: use ONLY user_data_dir (simple approach)
        # - Persistent Chrome profile at ~/.co/browser_profile/
        # - Stores cookies, localStorage, sessionStorage, cache, extensions, everything
        # - Survives browser restarts automatically
        # - No need for storage_state.json complexity (browser-use uses that for portability)

        # Patchright supplies the anti-detection defaults; we pass only run-environment
        # flags (see browser_config.py). executable_path pins real Chrome, which Patchright
        # recommends over bundled Chromium.
        self.browser = self.playwright.chromium.launch_persistent_context(
            str(profile_dir),  # Persistent profile at ~/.co/browser_profile/
            headless=headless,
            executable_path=chrome_path,
            args=CHROME_DEFAULT_ARGS,  # environment-stability flags only
            ignore_default_args=IGNORE_DEFAULT_ARGS + ['--use-mock-keychain'],  # macOS cookie fix
            proxy=_browser_proxy_from_env(),  # route egress through BROWSER_PROXY if set, else None
            timeout=120000,
        )

        # Seed a portable login state into the fresh context once, before any navigation, so a
        # deployed agent starts already signed in. launch_persistent_context() can't take
        # storage_state=, so the exported cookies are applied with add_cookies. A missing file
        # raises (fail loud): if a deploy declared a seed it must be packaged.
        if self._seed_state and not self._seeded:
            cookies = json.loads(Path(self._seed_state).read_text()).get("cookies", [])
            if cookies:
                self.browser.add_cookies(cookies)
            self._seeded = True

        # Create this session's tab in the freshly launched context (other sessions
        # get their own tab lazily on first use). _ensure_page applies the viewport
        # and anti-detection init script when it creates the tab.
        self._ensure_page(self._bound_session_key())

        if force and had_previous_browser_state:
            return f"Previous browser closed by force. Browser opened with persistent profile: {profile_dir}"
        if had_previous_browser_state:
            return f"Previous stale browser state closed. Browser opened with persistent profile: {profile_dir}"
        return f"Browser opened with persistent profile: {profile_dir}"

    @_no_auto_tab
    def save_state(self, path: str) -> str:
        """Export the current login state to a portable Playwright storage_state JSON.

        Writes {"cookies": [...], "origins": [...]} to `path`. Run this locally after logging
        in by hand (headed) to capture a session, then ship the file and pass it back as
        BrowserAutomation(seed_state=path) on the deployed agent. The JSON is plaintext and
        portable across machines/OSes; a copied Chrome profile is not (its cookies are
        encrypted per-OS).

        SECURITY: the file holds live session cookies — anyone with it can act as the
        logged-in user. Treat it as a secret: never commit it (add to .gitignore), don't
        bake it into a Docker image, and prefer injecting it via the deploy secret store.
        """
        if not self.browser:
            return "Browser not open"
        self.browser.storage_state(path=path)
        return (
            f"Saved login state to {path}. This file contains live session cookies — "
            f"keep it secret, add it to .gitignore, and never commit or bake it into an image."
        )

    def go_to(self, url: str, purpose: str = "", who: str = "", hours: float = 0.0) -> str:
        """Navigate to a URL.

        The FIRST navigation on an unoccupied tab must say who it's for and why:
        pass --purpose and --who (and optional --hours). Once a tab is occupied,
        later go_to calls navigate freely without repeating the flags, so multi-step
        flows keep working; pass the flags again only to re-label the active tab.
        """
        key = self._bound_session_key()
        existing = self._tab_meta.get(key, {})
        occupied = bool(existing.get("purpose") and existing.get("who"))
        if not occupied and not (purpose and who):
            raise ValueError(_occupancy_help("go_to", url))

        if not self.page:
            self.open_browser()

        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}' if '.' in url else f'http://{url}'

        self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
        self.page.wait_for_timeout(2000)
        self.current_url = self.page.url

        meta = self._tab_meta.setdefault(key, {"who": "", "purpose": "", "hours": 0.0, "opened_at": datetime.now()})
        if purpose:
            meta["purpose"] = purpose
        if who:
            meta["who"] = who
        if hours:
            meta["hours"] = hours

        self._save_context()
        return f"Navigated to {self.current_url}"

    @_no_auto_tab
    def newtab(self, url: str = "", purpose: str = "", who: str = "", hours: float = 0.0) -> str:
        """Open a new tab, record who occupies it and why, make it active. purpose+who required."""
        if not purpose or not who:
            raise ValueError(_occupancy_help("newtab", url or "<url>"))
        if not self.browser:
            self.open_browser()
        key = self._bound_session_key()
        self._ensure_page(key)                     # create THIS (new) session's tab
        self._tab_meta[key] = {"who": who, "purpose": purpose, "hours": hours, "opened_at": datetime.now()}
        if url:
            return self.go_to(url, purpose=purpose, who=who, hours=hours)
        return f"Opened new tab · who={who} · purpose={purpose!r}"

    @_no_auto_tab
    def tab_status(self) -> str:
        """Formatted list of registered tabs with owner, purpose, and how long each has been open.

        Renders from the tab REGISTRY (_tab_meta), so a tab reserved via `tab open`
        shows up immediately — before it has ever navigated — which is exactly when
        another agent needs to see it. A tab with no live page yet is marked
        'reserved'. Marks the active tab '*'.
        """
        if not self._tab_meta:
            return "Tabs: none"
        active = self._bound_session_key()
        lines = [f"Tabs ({len(self._tab_meta)}):"]
        for key, meta in list(self._tab_meta.items()):
            page = self._pages.get(key)
            if page is not None and callable(getattr(page, "is_closed", None)) and page.is_closed():
                page = None
            where = page.url if page is not None else "(reserved — no page yet)"
            marker = "*" if key == active else " "
            name = "main" if key is None else key
            who = meta.get("who") or "-"
            purpose = meta.get("purpose") or "-"
            line = f"  {marker}[{name}] {where}  who={who}  purpose={purpose!r}"
            opened_at = meta.get("opened_at")
            if opened_at:
                elapsed = (datetime.now() - opened_at).total_seconds()
                line += f"  open {_age(elapsed)}"
                hours = meta.get("hours") or 0
                if hours > 0:
                    line += f" · flagged {hours:g}h"
                    if elapsed > hours * 3600:
                        line += " — may be closed"
            last_at = meta.get("last_at")
            if last_at:
                last_line = (meta.get("last_line") or "")[:60]
                line += f'\n      last: "{last_line}" · {_age(time.time() - last_at)} ago'
            lines.append(line)
        return "\n".join(lines)

    @_no_auto_tab
    def close_tab(self, key: Optional[str] = None) -> str:
        """Close ONE session's tab (default = the current session's). The rest of the
        browser stays open — use close() to shut the whole browser down."""
        if not self.browser:
            return "Browser not open"
        # A tab reclaimed for idle/LRU keeps its registry entry with no live page; it is
        # still a real tab the caller may release, so accept a key known to EITHER store.
        if key not in self._pages and key not in self._tab_meta:
            return f"No open tab for {key!r}"
        error = self._close_tab(key)  # forget=True: drops both the page and the registry entry
        return error or "Tab closed"

    def find_element_by_description(self, description: str) -> str:
        """Find element using natural language description.

        Uses element_finder: LLM selects from indexed list, never generates CSS.

        Args:
            description: e.g., "the submit button", "email input field"

        Returns:
            Pre-built locator string, or error message
        """
        if not self.page:
            return "Browser not open"

        element = element_finder.find_element(self.page, description)
        if element:
            return element.locator
        return f"Could not find element matching: {description}"

    def click_element_by_selector(self, selector: str, index: int = 0, text: str = "", frame_url_contains: str = "", frame_name: str = "") -> str:
        """Click an element using a CSS selector via Playwright locator().

        Use when a workflow has a stable selector such as an aria-label,
        role-compatible attribute, or data-testid. `index` is zero-based.
        If `text` is provided, only visible elements with exactly that text are
        considered.

        Set frame_url_contains or frame_name to resolve the selector inside a page
        frame, including cross-origin iframes (e.g. an embedded widget or payment
        form) that main-page selectors can't reach. The click is dispatched through
        Playwright's input layer as a real pointer event at the element's
        coordinates. Frame targeting applies to the selector path; `text` matching
        is main-frame only.
        """
        if not self.page:
            return "Browser not open"

        if text:
            matches = self.page.evaluate(
                """
                (options) => {
                    const normalize = (el) => (el?.innerText || el?.textContent || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/[ \\t\\n]+/g, ' ')
                        .trim();
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            rect.width > 0 &&
                            rect.height > 0 &&
                            rect.bottom > 0 &&
                            rect.top < window.innerHeight;
                    };
                    return Array.from(document.querySelectorAll(options.selector))
                        .filter((el) => isVisible(el) && normalize(el) === options.text)
                        .map((el) => {
                            const rect = el.getBoundingClientRect();
                            return {
                                x: rect.x + rect.width / 2,
                                y: rect.y + rect.height / 2
                            };
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

            self.page.mouse.click(matches[index]["x"], matches[index]["y"])
            self._save_context()
            self.page.wait_for_timeout(1000)
            return f"Clicked element {index + 1}/{count} matching selector: {selector} with text: {text}"

        if frame_url_contains or frame_name:
            # Resolve inside matching page frames so cross-origin iframes (e.g. an
            # embedded widget) the main-page DOM can't reach are clickable.
            candidates = []
            for frame in self.page.frames:
                url = getattr(frame, "url", "") or ""
                name = getattr(frame, "name", "") or ""
                if frame_url_contains and frame_url_contains not in url:
                    continue
                if frame_name and frame_name != name:
                    continue
                loc = frame.locator(selector)
                candidates.extend(loc.nth(i) for i in range(loc.count()))
            where = f" in frames matching {(frame_url_contains or frame_name)!r}"
        else:
            loc = self.page.locator(selector)
            candidates = [loc.nth(i) for i in range(loc.count())]
            where = ""

        count = len(candidates)
        if count == 0:
            return f"No element found for selector: {selector}{where}"
        if index < 0 or index >= count:
            return f"Selector matched {count} elements{where}; index {index} is out of range"

        target = candidates[index]
        box = target.bounding_box()
        if box:
            self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        else:
            target.click(force=True)

        self._save_context()
        self.page.wait_for_timeout(1000)
        return f"Clicked element {index + 1}/{count} matching selector: {selector}{where}"

    def count_elements_by_selector(self, selector: str) -> str:
        """Count elements matching a CSS selector via Playwright locator()."""
        if not self.page:
            return "Browser not open"

        count = self.page.locator(selector).count()
        return f"{count} element{'s' if count != 1 else ''} match selector: {selector}"

    def get_element_text_by_selector(self, selector: str, index: int = 0) -> str:
        """Get inner text from an element using a CSS selector via Playwright locator()."""
        if not self.page:
            return "Browser not open"

        locator = self.page.locator(selector)
        count = locator.count()
        if count == 0:
            return f"No element found for selector: {selector}"
        if index < 0 or index >= count:
            return f"Selector matched {count} elements; index {index} is out of range"

        return locator.nth(index).inner_text()

    def type_text_by_selector(self, selector: str, text: str, index: int = 0) -> str:
        """Focus an element by CSS selector and type text via Playwright keyboard."""
        if not self.page:
            return "Browser not open"

        locator = self.page.locator(selector)
        count = locator.count()
        if count == 0:
            return f"No element found for selector: {selector}"
        if index < 0 or index >= count:
            return f"Selector matched {count} elements; index {index} is out of range"

        target = locator.nth(index)
        target.click(force=True)
        self.page.keyboard.type(text)
        self.page.wait_for_timeout(1000)
        return f"Typed text into element {index + 1}/{count} matching selector: {selector}"

    def upload_file_by_selector(
        self,
        selector: str,
        file_path: str,
        index: int = 0,
        frame_url_contains: str = "",
        frame_name: str = "",
    ) -> str:
        """Upload a local file into an existing `<input type=file>` selector.

        This is frame-aware because many logged-in apps render editors inside
        iframes. The selector should point to a file input, often
        `input[type="file"]`. Hidden file inputs are allowed; Playwright can set
        files on them directly.
        """
        if not self.page:
            return "Browser not open"

        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return f"File not found: {path}"
        if not path.is_file():
            return f"Path is not a file: {path}"

        matches = []
        for frame_index, frame in enumerate(self.page.frames):
            url = getattr(frame, "url", "") or ""
            raw_name = getattr(frame, "name", "") or ""
            name = raw_name() if callable(raw_name) else raw_name
            if frame_url_contains and frame_url_contains not in url:
                continue
            if frame_name and frame_name != name:
                continue

            locator = frame.locator(selector)
            count = locator.count()
            for locator_index in range(count):
                matches.append((frame_index, name, url, locator.nth(locator_index)))

        if not matches:
            return f"No file input found for selector: {selector}"
        if index < 0 or index >= len(matches):
            return f"Selector matched {len(matches)} file input(s); index {index} is out of range"

        frame_index, name, url, target = matches[index]
        target.set_input_files(str(path))
        self.page.wait_for_timeout(1500)
        self._save_context()
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

    def upload_file_after_click_by_selector(
        self,
        click_selector: str,
        file_path: str,
        index: int = 0,
        text: str = "",
        frame_url_contains: str = "",
        frame_name: str = "",
        timeout_ms: int = 5000,
    ) -> str:
        """Click a control that opens a file chooser, then upload a local file.

        Use this when the app exposes an upload button such as "Upload from
        computer" instead of a stable visible file input.
        """
        if not self.page:
            return "Browser not open"

        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return f"File not found: {path}"
        if not path.is_file():
            return f"Path is not a file: {path}"

        matches = []
        for frame_index, frame in enumerate(self.page.frames):
            url = getattr(frame, "url", "") or ""
            raw_name = getattr(frame, "name", "") or ""
            name = raw_name() if callable(raw_name) else raw_name
            if frame_url_contains and frame_url_contains not in url:
                continue
            if frame_name and frame_name != name:
                continue

            locator = frame.locator(click_selector)
            count = locator.count()
            for locator_index in range(count):
                target = locator.nth(locator_index)
                if text:
                    try:
                        candidate_text = target.inner_text().replace("\u00a0", " ").strip()
                    except Exception:
                        candidate_text = ""
                    if candidate_text != text:
                        continue
                matches.append((frame_index, name, url, target))

        if not matches:
            suffix = f" with text: {text}" if text else ""
            return f"No upload trigger found for selector: {click_selector}{suffix}"
        if index < 0 or index >= len(matches):
            return f"Selector matched {len(matches)} upload trigger(s); index {index} is out of range"

        frame_index, name, url, target = matches[index]
        with self.page.expect_file_chooser(timeout=timeout_ms) as chooser_info:
            target.click(force=True)
        chooser = chooser_info.value
        chooser.set_files(str(path))
        self.page.wait_for_timeout(2500)
        self._save_context()
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

    def _load_script_args(self, script_path: str, args_json: str) -> tuple[Optional[str], Optional[dict], Optional[str]]:
        path = Path(script_path).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            return None, None, f"Script not found: {path}"
        if not path.is_file():
            return None, None, f"Script path is not a file: {path}"

        try:
            args = json.loads(args_json or "{}")
        except json.JSONDecodeError as exc:
            return None, None, f"Invalid args_json: {exc}"

        script = path.read_text(encoding="utf-8")
        return script, args, None

    def run_page_script(self, script_path: str, args_json: str = "{}") -> str:
        """Run a local JavaScript file in the main page and return JSON.

        The script should evaluate to a function, for example `(args) => ({ ok: true })`.
        Use this for skill-owned DOM extraction or verification while sharing the
        current browser page, cookies, and login context.

        For pages that render important UI in iframes, use `run_frame_script(...)`.
        """
        if not self.page:
            return "Browser not open"

        script, args, error = self._load_script_args(script_path, args_json)
        if error:
            return error

        result = self.page.evaluate(script, args)
        return json.dumps(result, indent=2, ensure_ascii=False)

    def run_frame_script(
        self,
        script_path: str,
        args_json: str = "{}",
        frame_url_contains: str = "",
        frame_name: str = "",
        first_ok: bool = True,
    ) -> str:
        """Run a local JavaScript file in page frames and return JSON.

        The script should evaluate to a function, for example `(args) => ({ ok: true })`.
        This is useful for sites that render modals or controls in iframes. The
        script is run in each matching frame with the same `args_json`.

        Args:
            script_path: Local JavaScript file path.
            args_json: JSON object passed to the script.
            frame_url_contains: Optional substring that the frame URL must contain.
            frame_name: Optional exact frame name to target.
            first_ok: If true, return as soon as a frame returns an object with `ok: true`.

        Returns:
            JSON with `ok`, `matched_frame`, and scanned `frames`.
        """
        if not self.page:
            return "Browser not open"

        script, args, error = self._load_script_args(script_path, args_json)
        if error:
            return error

        frames = []
        matched = None

        for index, frame in enumerate(self.page.frames):
            url = getattr(frame, "url", "") or ""
            raw_name = getattr(frame, "name", "") or ""
            name = raw_name() if callable(raw_name) else raw_name
            if frame_url_contains and frame_url_contains not in url:
                continue
            if frame_name and frame_name != name:
                continue

            frame_info = {
                "index": index,
                "name": name,
                "url": url,
                "ok": False,
                "result": None,
                "error": None,
            }

            try:
                result = frame.evaluate(script, args)
                frame_info["result"] = result
                frame_info["ok"] = bool(isinstance(result, dict) and result.get("ok") is True)
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

    def click_element_near_selector(
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
        """Click a visible target element near a visible anchor element.

        This is useful for workflows where a skill knows the stable selectors but
        a page has many repeated buttons with the same label. Selectors and text
        come from the skill; this helper only applies generic DOM proximity rules.
        Negative `anchor_index` values count from the end of the visible matches.
        """
        if not self.page:
            return "Browser not open"

        target = self.page.evaluate(
            """
            (options) => {
                const normalize = (el) => (el?.innerText || el?.textContent || '')
                    .replace(/\\u00a0/g, ' ')
                    .replace(/[ \\t\\n]+/g, ' ')
                    .trim();
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        rect.width > 0 &&
                        rect.height > 0 &&
                        rect.bottom > 0 &&
                        rect.top < window.innerHeight;
                };
                const isEnabled = (button) =>
                    !button.disabled && button.getAttribute('aria-disabled') !== 'true';
                const textMatches = (el) => !options.target_text || normalize(el) === options.target_text;
                const anchors = Array.from(document.querySelectorAll(options.anchor_selector))
                    .filter((anchor) => isVisible(anchor))
                    .filter((anchor) => !options.require_anchor_text || normalize(anchor).length > 0);

                if (!anchors.length) {
                    return { ok: false, error: `No visible anchor found for selector: ${options.anchor_selector}` };
                }

                let anchorIndex = options.anchor_index;
                if (anchorIndex < 0) anchorIndex = anchors.length + anchorIndex;
                if (anchorIndex < 0 || anchorIndex >= anchors.length) {
                    return {
                        ok: false,
                        error: `Anchor selector matched ${anchors.length} elements; index ${options.anchor_index} is out of range`
                    };
                }

                const anchor = anchors[anchorIndex];
                const anchorRect = anchor.getBoundingClientRect();
                let container = null;
                if (options.container_selector) {
                    container = anchor.closest(options.container_selector);
                }
                container = container || anchor.closest('form') || anchor.parentElement || document.body;

                const targetsInContainer = Array.from(container.querySelectorAll(options.target_selector))
                    .filter((candidate) => isVisible(candidate) && isEnabled(candidate) && textMatches(candidate));

                let target = targetsInContainer
                    .map((candidate) => ({ candidate, rect: candidate.getBoundingClientRect() }))
                    .filter(({ rect }) => rect.top >= anchorRect.top - 8)
                    .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left)[0]?.candidate;

                if (!target) {
                    target = Array.from(document.querySelectorAll(options.target_selector))
                        .filter((candidate) =>
                            isVisible(candidate) &&
                            isEnabled(candidate) &&
                            textMatches(candidate)
                        )
                        .map((candidate) => ({ candidate, rect: candidate.getBoundingClientRect() }))
                        .filter(({ rect }) => rect.top >= anchorRect.top - 8)
                        .sort((a, b) =>
                            Math.abs(a.rect.top - anchorRect.top) - Math.abs(b.rect.top - anchorRect.top) ||
                            a.rect.left - b.rect.left
                        )[0]?.candidate;
                }

                if (!target) {
                    return {
                        ok: false,
                        error: `No visible enabled target found near anchor for selector: ${options.target_selector}`,
                        anchor_text: normalize(anchor)
                    };
                }

                const rect = target.getBoundingClientRect();
                return {
                    ok: true,
                    x: rect.x + rect.width / 2,
                    y: rect.y + rect.height / 2,
                    anchor_text: normalize(anchor),
                    target_text: normalize(target)
                };
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
            return target.get("error", "Could not find target near anchor") if target else "Could not find target near anchor"

        self.page.mouse.click(target["x"], target["y"])
        self.page.wait_for_timeout(wait_ms)
        self._save_context()

        state = "clicked"
        if verify_anchor_text_cleared:
            state = self.page.evaluate(
                """
                (options) => {
                    const normalize = (el) => (el?.innerText || el?.textContent || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/[ \\t\\n]+/g, ' ')
                        .trim();
                    const isVisible = (el) => {
                        if (!el) return false;
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' &&
                            style.visibility !== 'hidden' &&
                            rect.width > 0 &&
                            rect.height > 0 &&
                            rect.bottom > 0 &&
                            rect.top < window.innerHeight;
                    };
                    const matchingAnchor = Array.from(document.querySelectorAll(options.anchor_selector))
                        .find((anchor) => isVisible(anchor) && normalize(anchor) === options.anchor_text);
                    return matchingAnchor ? 'uncertain_anchor_still_contains_text' : 'anchor_text_cleared';
                }
                """,
                {"anchor_selector": anchor_selector, "anchor_text": target["anchor_text"]},
            )

        return (
            "Clicked target near anchor; "
            f"state={state}; anchor_text={target['anchor_text']!r}; target_text={target['target_text']!r}"
        )

    def click(self, description: str) -> str:
        """Click on an element using natural language description.

        Uses element_finder: LLM selects from pre-built locators, never generates CSS.
        """
        if not self.page:
            return "Browser not open"

        element = element_finder.find_element(self.page, description)

        # Get the appropriate locator context (main page, iframe, or shadow DOM)
        if element.frame.startswith("shadow-"):
            # Shadow DOM element — use coordinates directly (locators can't pierce shadow DOM)
            import time as _time
            x = element.x + element.width // 2
            y = element.y + element.height // 2
            self.page.mouse.click(x, y)
            self._save_context()
            _time.sleep(1)
            print(f"\n[browser] CLICKED (shadow DOM) element [{element.index}] {element.tag} text='{element.text}' at ({x},{y})\n")
            return f"Clicked [{element.index}] {element.tag} '{element.text}' (shadow DOM)"

        if element.frame != "main":
            # Element is inside an iframe - find the frame first
            frame = None
            for f in self.page.frames:
                if f.name == element.frame or (hasattr(f, '_impl') and element.frame in (f.url or "")):
                    frame = f
                    break

            if frame:
                locator = frame.locator(element.locator)
                print(f"[browser] DEBUG: Element in iframe '{element.frame}', using frame locator")
            else:
                locator = self.page.locator(element.locator)
                print(f"[browser] WARNING: Iframe '{element.frame}' not found, using main page locator")
        else:
            # Element is in main document
            locator = self.page.locator(element.locator)

        import time as _time

        if locator.count() > 0:
            box = locator.first.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                self.page.mouse.click(x, y)
                self._save_context()
                _time.sleep(1)  # Wait for DOM changes (modals, dropdowns, etc.)
                print(f"\n[browser] CLICKED element [{element.index}] {element.tag} text='{element.text}' at ({x:.0f},{y:.0f})\n")
                return f"Clicked [{element.index}] {element.tag} '{element.text}'"

            locator.first.click(force=True)
            self._save_context()
            _time.sleep(1)
            print(f"\n[browser] CLICKED (force) element [{element.index}] {element.tag} text='{element.text}'\n")
            return f"Clicked [{element.index}] {element.tag} '{element.text}' (force)"

        # Fallback: use original coordinates
        x = element.x + element.width // 2
        y = element.y + element.height // 2
        self.page.mouse.click(x, y)
        self._save_context()
        _time.sleep(1)
        print(f"\n[browser] CLICKED (coords) element [{element.index}] text='{element.text}' at ({x},{y})\n")
        return f"Clicked [{element.index}] '{element.text}' at ({x}, {y})"

    def mouse_click(self, x: int, y: int) -> str:
        """Click at exact screen coordinates. Use after hover() to click items in
        hover menus (like LinkedIn reactions) without re-scanning the DOM which
        would dismiss the menu."""
        if not self.page:
            return "Browser not open"
        import time as _time
        self.page.mouse.click(x, y)
        _time.sleep(1)
        print(f"\n[browser] CLICKED at ({x},{y})\n")
        return f"Clicked at ({x}, {y})"

    def hover(self, description: str) -> str:
        """Hover over an element using natural language description.

        Moves the mouse over the element without clicking. Useful for triggering
        hover menus, tooltips, and reaction pickers (e.g. LinkedIn reactions).
        """
        if not self.page:
            return "Browser not open"

        element = element_finder.find_element(self.page, description)
        import time as _time

        if element.frame.startswith("shadow-"):
            x = element.x + element.width // 2
            y = element.y + element.height // 2
            self.page.mouse.move(x, y)
        elif element.frame != "main":
            frame = None
            for f in self.page.frames:
                if f.name == element.frame or (hasattr(f, '_impl') and element.frame in (f.url or "")):
                    frame = f
                    break
            locator = frame.locator(element.locator) if frame else self.page.locator(element.locator)
            if locator.count() > 0:
                locator.first.hover()
            else:
                self.page.mouse.move(element.x + element.width // 2, element.y + element.height // 2)
        else:
            locator = self.page.locator(element.locator)
            if locator.count() > 0:
                locator.first.hover()
            else:
                self.page.mouse.move(element.x + element.width // 2, element.y + element.height // 2)

        _time.sleep(1)
        print(f"\n[browser] HOVERED element [{element.index}] {element.tag} text='{element.text}'\n")
        return f"Hovered [{element.index}] {element.tag} '{element.text}'"

    def right_click(self, description: str) -> str:
        """Right-click on an element using natural language description.

        Opens context menus. Uses element_finder for AI-powered element matching.
        """
        if not self.page:
            return "Browser not open"

        element = element_finder.find_element(self.page, description)
        import time as _time

        if element.frame.startswith("shadow-"):
            x = element.x + element.width // 2
            y = element.y + element.height // 2
            self.page.mouse.click(x, y, button="right")
            _time.sleep(1)
            print(f"\n[browser] RIGHT-CLICKED (shadow DOM) element [{element.index}] {element.tag} text='{element.text}' at ({x},{y})\n")
            return f"Right-clicked [{element.index}] {element.tag} '{element.text}' (shadow DOM)"

        if element.frame != "main":
            frame = None
            for f in self.page.frames:
                if f.name == element.frame or (hasattr(f, '_impl') and element.frame in (f.url or "")):
                    frame = f
                    break
            locator = frame.locator(element.locator) if frame else self.page.locator(element.locator)
        else:
            locator = self.page.locator(element.locator)

        if locator.count() > 0:
            box = locator.first.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                self.page.mouse.click(x, y, button="right")
                _time.sleep(1)
                print(f"\n[browser] RIGHT-CLICKED element [{element.index}] {element.tag} text='{element.text}' at ({x:.0f},{y:.0f})\n")
                return f"Right-clicked [{element.index}] {element.tag} '{element.text}'"

        x = element.x + element.width // 2
        y = element.y + element.height // 2
        self.page.mouse.click(x, y, button="right")
        _time.sleep(1)
        print(f"\n[browser] RIGHT-CLICKED (coords) element [{element.index}] text='{element.text}' at ({x},{y})\n")
        return f"Right-clicked [{element.index}] '{element.text}' at ({x}, {y})"

    def double_click(self, description: str) -> str:
        """Double-click on an element using natural language description.

        Useful for selecting text, opening items, or triggering double-click actions.
        """
        if not self.page:
            return "Browser not open"

        element = element_finder.find_element(self.page, description)
        import time as _time

        if element.frame.startswith("shadow-"):
            x = element.x + element.width // 2
            y = element.y + element.height // 2
            self.page.mouse.dblclick(x, y)
            _time.sleep(1)
            print(f"\n[browser] DOUBLE-CLICKED (shadow DOM) element [{element.index}] {element.tag} text='{element.text}' at ({x},{y})\n")
            return f"Double-clicked [{element.index}] {element.tag} '{element.text}' (shadow DOM)"

        if element.frame != "main":
            frame = None
            for f in self.page.frames:
                if f.name == element.frame or (hasattr(f, '_impl') and element.frame in (f.url or "")):
                    frame = f
                    break
            locator = frame.locator(element.locator) if frame else self.page.locator(element.locator)
        else:
            locator = self.page.locator(element.locator)

        if locator.count() > 0:
            box = locator.first.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                self.page.mouse.dblclick(x, y)
                _time.sleep(1)
                print(f"\n[browser] DOUBLE-CLICKED element [{element.index}] {element.tag} text='{element.text}' at ({x:.0f},{y:.0f})\n")
                return f"Double-clicked [{element.index}] {element.tag} '{element.text}'"

        x = element.x + element.width // 2
        y = element.y + element.height // 2
        self.page.mouse.dblclick(x, y)
        _time.sleep(1)
        print(f"\n[browser] DOUBLE-CLICKED (coords) element [{element.index}] text='{element.text}' at ({x},{y})\n")
        return f"Double-clicked [{element.index}] '{element.text}' at ({x}, {y})"

    def keyboard_type(self, text: str) -> str:
        """Type text using keyboard input (Playwright keyboard API wrapper).

        Simulates keyboard typing character by character into the currently focused element.
        Works with any element type (input, textarea, contenteditable, etc).

        Args:
            text: The text to type

        Returns:
            Success message with system reminder to verify with screenshot
        """
        if not self.page:
            return "Browser not open"

        self.page.keyboard.type(text)

        return f"""Typed: '{text}'

SYSTEM REMINDER: Please use take_screenshot() to verify the text was typed into the correct input box. If the text is NOT visible in the expected location, you may need to click the element first to focus it, then type again."""

    def keyboard_press(self, key: str) -> str:
        """Press a keyboard key or key combination.

        Use for special keys and shortcuts — NOT for typing text.
        For typing text use keyboard_type() instead.

        Args:
            key: Key name or combo, e.g. "Enter", "Escape", "Tab",
                 "Control+Enter", "Control+x", "Meta+a", "Shift+Tab"

        Returns:
            Success message
        """
        if not self.page:
            return "Browser not open"

        self.page.keyboard.press(key)
        return f"Pressed: '{key}'"

    def get_system_info(self) -> str:
        """Get the operating system info. Call this before using keyboard shortcuts so you know which modifier key to use (Meta on macOS, Control on Windows/Linux)."""
        system = platform.system()
        if system == "Darwin":
            return "OS: macOS. Use Meta for shortcuts (Meta+a select all, Meta+c copy, Meta+v paste, Meta+z undo)."
        elif system == "Windows":
            return "OS: Windows. Use Control for shortcuts (Control+a select all, Control+c copy, Control+v paste, Control+z undo)."
        return "OS: Linux. Use Control for shortcuts (Control+a select all, Control+c copy, Control+v paste, Control+z undo)."

    def get_text(self) -> str:
        """Get all visible text from the page."""
        if not self.page:
            return "Browser not open"
        return self.page.inner_text("body")

    def extract_items_by_selector(
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
        """Extract repeated visible items from a page using skill-provided selectors.

        Returns JSON with item text, optional author metadata, optional action
        index among all matching visible actions, and visible bounds.
        """
        if not self.page:
            return "Browser not open"

        items = self.page.evaluate(
            """
            (options) => {
                const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style.display !== 'none' &&
                        style.visibility !== 'hidden' &&
                        rect.width > 0 &&
                        rect.height > 0 &&
                        rect.bottom > 0 &&
                        rect.top < window.innerHeight;
                };

                const textOf = (el) => (el?.innerText || el?.textContent || '')
                    .replace(/\\u00a0/g, ' ')
                    .replace(/[ \\t]+/g, ' ')
                    .replace(/\\n{3,}/g, '\\n\\n')
                    .trim();

                const textMatches = (el, expectedText) => !expectedText || textOf(el) === expectedText;
                const excludePattern = options.exclude_text_pattern
                    ? new RegExp(options.exclude_text_pattern, 'i')
                    : null;
                const actions = options.action_selector
                    ? Array.from(document.querySelectorAll(options.action_selector))
                        .filter((action) => isVisible(action) && textMatches(action, options.action_text))
                    : [];

                const result = [];
                const containers = Array.from(document.querySelectorAll(options.container_selector));

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

                    const action = actions.find((candidate) => container.contains(candidate));

                    result.push({
                        item_index: result.length,
                        author,
                        text,
                        action_index: action ? actions.indexOf(action) : null,
                        has_action: Boolean(action),
                        visible_bounds: {
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
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

    def get_current_url(self) -> str:
        """Get the current page URL."""
        if not self.page:
            return "Browser not open"
        return self.page.url

    def save_page_context(self, name: str = "page") -> str:
        """Save current HTML, CSS, and clickable element data under ~/.co."""
        if not self.page:
            return "Browser not open"

        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name).strip("._-") or "page"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path.home() / ".co" / "browser_context" / f"{timestamp}_{safe_name}"
        out_dir.mkdir(parents=True, exist_ok=True)

        html_path = out_dir / "page.html"
        css_path = out_dir / "styles.css"
        elements_path = out_dir / "elements.json"

        html_path.write_text(self.page.content(), encoding="utf-8")

        css = self.page.evaluate("""
            () => Array.from(document.styleSheets).map((sheet, i) => {
                try {
                    return `/* ${sheet.href || `inline-${i}`} */\\n` +
                        Array.from(sheet.cssRules || []).map(rule => rule.cssText).join("\\n");
                } catch (error) {
                    return `/* ${sheet.href || `stylesheet-${i}`} unavailable: ${error.name} */`;
                }
            }).join("\\n\\n")
        """)
        css_path.write_text(css, encoding="utf-8")

        elements = element_finder.extract_elements(self.page)
        element_dicts = [
            element.model_dump() if hasattr(element, "model_dump") else element.dict()
            for element in elements
        ]
        elements_path.write_text(json.dumps(element_dicts, indent=2), encoding="utf-8")

        return (
            f"Saved page context to {out_dir}\n"
            f"- HTML: {html_path}\n"
            f"- CSS: {css_path}\n"
            f"- Elements: {elements_path}\n"
            f"- URL: {self.page.url}\n"
            f"- Elements: {len(element_dicts)}"
        )

    def take_screenshot(self, path: str = None, full_page: bool = False) -> str:
        """Take a screenshot of the current page and return base64 encoded image.

        Args:
            path: Optional path for the screenshot
            full_page: If True, captures entire page height (may lose details but shows overview)

        Returns:
            Base64 encoded image data
        """
        if not BROWSER_AVAILABLE:
            return 'Browser tools not installed. Run: pip install patchright && patchright install chrome'

        if not self.page:
            return "Browser not open"

        os.makedirs(self.screenshots_dir, exist_ok=True)

        if not path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"step_{timestamp}.png"

        if not "/" in path:
            path = f"{self.screenshots_dir}/{path}"

        screenshot_bytes = self.page.screenshot(path=path, full_page=full_page)
        self.last_screenshot_path = path

        # Print where screenshot was saved
        print(f"\n[browser] Screenshot saved to: {path}")
        print(f"[browser] Full page: {full_page}, Size: {len(screenshot_bytes)} bytes\n")

        # Bound the payload. The screenshot is sent to the frontend as a base64 data URL
        # in ONE relay WebSocket frame; base64 inflates bytes ~33% and the relay's default
        # cap is 1 MB (websockets max_size), so a frame over it drops the relay connection
        # (and reconnect replays it, so the agent flaps offline). A dense 1920-wide page is
        # a ~800 KB PNG = >1 MB base64. Re-encode only oversized captures as JPEG
        # (Playwright-native, no Pillow); keep PNG for the common case so text stays sharp.
        mime = "image/png"
        if len(screenshot_bytes) > 600_000:   # ~800 KB base64 + JSON, safely under 1 MB
            screenshot_bytes = self.page.screenshot(full_page=full_page, type="jpeg", quality=85)
            mime = "image/jpeg"
            print(f"[browser] oversized PNG re-encoded as JPEG q85: {len(screenshot_bytes)} bytes\n")

        # Wait for page to stabilize after screenshot (especially for full_page which scrolls/resizes)
        # This prevents focus loss when typing after taking a screenshot
        self.page.wait_for_timeout(1000)

        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return f"data:{mime};base64,{screenshot_base64}"

    def set_viewport(self, width: int, height: int) -> str:
        """Set the browser viewport size."""
        if not self.page:
            return "Browser not open"
        self.page.set_viewport_size({"width": width, "height": height})
        return f"Viewport set to {width}x{height}"

    def select_option(self, field_description: str, option: str) -> str:
        """Select an option from a dropdown."""
        if not self.page:
            return "Browser not open"

        selector = self.find_element_by_description(field_description)
        if selector.startswith("Could not"):
            return selector

        self.page.select_option(selector, label=option)
        return f"Selected '{option}' in {field_description}"

    def check_checkbox(self, description: str, checked: bool = True) -> str:
        """Check or uncheck a checkbox."""
        if not self.page:
            return "Browser not open"

        selector = self.find_element_by_description(description)
        if selector.startswith("Could not"):
            return selector

        if checked:
            self.page.check(selector)
            return f"Checked {description}"
        else:
            self.page.uncheck(selector)
            return f"Unchecked {description}"

    def wait_for_element(self, description: str, timeout: int = 30) -> str:
        """Wait for an element to appear."""
        if not self.page:
            return "Browser not open"

        selector = self.find_element_by_description(description)
        if selector.startswith("Could not"):
            self.page.wait_for_selector(f"text='{description}'", timeout=timeout * 1000)
            return f"Found text: '{description}'"

        self.page.wait_for_selector(selector, timeout=timeout * 1000)
        return f"Element appeared: {description}"

    def wait_for_text(self, text: str, timeout: int = 30) -> str:
        """Wait for specific text to appear on the page."""
        if not self.page:
            return "Browser not open"

        self.page.wait_for_selector(f"text='{text}'", timeout=timeout * 1000)
        return f"Found text: '{text}'"

    def wait(self, seconds: float) -> str:
        """Wait for a specified number of seconds."""
        if not self.page:
            return "Browser not open"
        self.page.wait_for_timeout(seconds * 1000)
        return f"Waited for {seconds} seconds"

    def scroll(self, times: int = 5, description: str = "the main content area") -> str:
        """Universal scroll with AI strategy and fallback.

        Tries: AI-generated → Element scroll → Page scroll
        Verifies success with screenshot comparison.
        """
        from . import scroll
        result = scroll.scroll(self.page, self.take_screenshot, times, description)
        self._save_context()
        return result

    def wait_for_manual_login(self, site_name: str = "the website") -> str:
        """Pause automation for user to login manually.

        Useful for sites with 2FA or other interactive sign-in steps.

        Args:
            site_name: Name of the site (e.g., "Gmail")

        Returns:
            Confirmation when user is ready to continue
        """
        if not self.page:
            return "Browser not open"

        # Manual login needs an interactive terminal. A hosted deploy has no stdin,
        # and every public method runs on the one shared browser worker thread —
        # blocking on input() there would freeze every other session's browser
        # indefinitely. Refuse fast; hosted agents sign in via save_state/seed_state.
        if not sys.stdin or not sys.stdin.isatty():
            return (
                "Manual login needs an interactive terminal, which a hosted deploy "
                "doesn't have. Capture the login locally with save_state(path) and "
                "start the deployed browser with seed_state=<path>."
            )

        print(f"\n{'='*60}")
        print(f"  MANUAL LOGIN REQUIRED")
        print(f"{'='*60}")
        print(f"Please login to {site_name} in the browser window.")
        print(f"Once you're logged in and ready to continue:")
        print(f"  Type 'yes' or 'Y' and press Enter")
        print(f"{'='*60}\n")

        while True:
            response = input("Ready to continue? (yes/Y): ").strip().lower()
            if response in ['yes', 'y']:
                print("Continuing automation...\n")
                self._save_context()
                return f"User confirmed login to {site_name} - continuing"
            else:
                print("Please type 'yes' or 'Y' when ready.")

    def extract_data(self, selector: str) -> List[str]:
        """Extract text from elements matching a selector."""
        if not self.page:
            return []

        elements = self.page.locator(selector)
        count = elements.count()
        return [elements.nth(i).inner_text() for i in range(count)]

    def get_links_from_page(self, domain_filter: str = "") -> List[str]:
        """Extract all unique links from the current page, optionally filtered by domain.

        Args:
            domain_filter: Only return URLs containing this string (e.g. "x.com/status")
        """
        if not self.page:
            return []

        urls = self.page.evaluate("""
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
        """, domain_filter)
        return urls or []

    def _save_context(self) -> None:
        """Force save browser state to disk.

        Called after critical actions (login, navigation) to ensure
        context is persisted even if process crashes.

        With launch_persistent_context(), Playwright automatically saves:
        - Cookies
        - localStorage
        - sessionStorage
        - IndexedDB
        - Service workers
        - Cache

        This method just waits briefly to ensure async saves complete.
        """
        if not self.browser or not self.page:
            return

        # Wait for any async operations to complete
        # Playwright's persistent context auto-saves in background
        self.page.wait_for_timeout(500)

    @_no_auto_tab
    def close(self) -> str:
        """Close the browser. A bound session (hosted multi-session) closes only its OWN tab;
        an unbound caller (single-session CLI / context-manager exit) tears the whole context
        down. Closing the shared context for one session would kill every other session's tab,
        so per-session callers must never reach the full teardown."""
        key = self._bound_session_key()
        if key is not None:
            err = self._close_tab(key)
            return f"close tab failed: {err}" if err else "Closed this session's browser tab."
        return self._teardown()

    def _teardown(self) -> str:
        """Tear the whole shared browser/context down and clear state. Underscore-prefixed so
        it is never exposed as a per-session LLM tool; called only from close() (unbound) and
        open_browser, both already on the browser worker thread."""
        cleanup_errors = []
        try:
            self._save_context()
        except Exception as exc:
            cleanup_errors.append(f"save context failed: {exc}")

        for key in list(self._pages):     # close every session's tab
            err = self._close_tab(key)
            if err:
                cleanup_errors.append(err)
        try:
            if self.browser:
                self.browser.close()
        except Exception as exc:
            cleanup_errors.append(f"close browser failed: {exc}")
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception as exc:
            cleanup_errors.append(f"stop playwright failed: {exc}")

        self._pages.clear()
        self._page_used.clear()
        self._page_url.clear()
        self.browser = None
        self.playwright = None
        if cleanup_errors:
            return "Browser closed with cleanup warnings: " + "; ".join(cleanup_errors)
        return "Browser closed"

    def __enter__(self):
        """Context manager entry - browser already initialized in __init__."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures browser closes and saves context."""
        self.close()
        return False
