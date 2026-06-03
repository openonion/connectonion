"""
Purpose: Natural language browser automation via Playwright with persistent profile and auto-save
LLM-Note:
  Dependencies: imports from [playwright.sync_api, connectonion Agent/llm_do, cli/browser_agent/element_finder, pydantic, pathlib, dotenv] | imported by [cli/commands/browser_commands.py] | tested by [tests/e2e/cli/test_browser_agent.py]
  Data flow: BrowserAutomation() initializes Playwright → opens browser with persistent context → provides tools (navigate, find_element, click, type_text, screenshot, scroll, wait_for_login) → auto-saves cookies after each critical action → Agent uses these tools via natural language → element_finder.py uses vision LLM to locate elements | screenshots saved to .tmp/ directory
  State/Effects: maintains browser/page/context state | persistent profile at ~/.co/browser_profile/ | auto-saves cookies after navigation and manual login | writes screenshots to .tmp/{timestamp}.png | modifies form_data dict for form fills | context manager ensures cleanup
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
import json
import platform
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

# Check Playwright availability
try:
    from playwright.sync_api import sync_playwright, Page, Browser, Playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Path to the browser agent system prompt


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

    def __init__(self, use_chrome_profile: bool = True, headless: bool = False):
        """Initialize browser automation.

        Args:
            use_chrome_profile: If True, uses your Chrome cookies/sessions.
                               Chrome must be closed before running.
            headless: If True, browser runs without visible window (default True).
        """
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.current_url: str = ""
        self.form_data: Dict[str, Any] = {}
        self.use_chrome_profile = use_chrome_profile
        self._screenshots = []
        self._headless = headless
        self.screenshots_dir = str(SCREENSHOTS_DIR)

    def _browser_is_usable(self) -> bool:
        """Return True when the current Playwright page can still be operated."""
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

    def open_browser(self, headless: bool = None, force: bool = False) -> str:
        """Open a new browser window.

        Args:
            headless: If True, browser runs without visible window. Defaults to the value set in __init__.
            force: If True, close the current browser first and open a fresh context.

        Note: If use_chrome_profile=True, Chrome must be completely closed.
        """
        if headless is None:
            headless = self._headless
        if not PLAYWRIGHT_AVAILABLE:
            return "Browser tools not installed. Run: pip install playwright && playwright install chromium"

        if self._browser_is_usable():
            if not force:
                return "<system-reminder>Browser already open and usable. Continue using the current browser page.</system-reminder>"
            self.close()
            had_previous_browser_state = True
        else:
            had_previous_browser_state = bool(self.browser or self.page or self.playwright)
            if had_previous_browser_state:
                self.close()

        self.playwright = sync_playwright().start()

        # Dedicated persistent profile owned by co
        # First run: fresh profile, user logs in once. All later runs reuse saved cookies.
        profile_dir = Path.home() / ".co" / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        # Remove --no-sandbox from args since Playwright adds it by default
        # Just keep the flags we actually need
        # NOTE: --use-mock-keychain removed to fix cookie persistence on macOS
        # See: https://github.com/microsoft/playwright/issues/31736
        # Can test removing this in the future if cookie issues persist

        # Use Google Chrome instead of Chromium for better X.com compatibility
        chrome_path = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
        if not os.path.exists(chrome_path):
            chrome_path = None  # Fall back to Chromium if Chrome not installed

        # Session persistence: use ONLY user_data_dir (simple approach)
        # - Persistent Chrome profile at ~/.co/browser_profile/
        # - Stores cookies, localStorage, sessionStorage, cache, extensions, everything
        # - Survives browser restarts automatically
        # - No need for storage_state.json complexity (browser-use uses that for portability)

        # Launch browser with browser-use anti-detection config (see browser_config.py)
        self.browser = self.playwright.chromium.launch_persistent_context(
            str(profile_dir),  # Persistent profile at ~/.co/browser_profile/
            headless=headless,
            executable_path=chrome_path,
            args=CHROME_DEFAULT_ARGS,  # 53 args + 30 disabled features from browser-use
            ignore_default_args=IGNORE_DEFAULT_ARGS + ['--use-mock-keychain'],  # + macOS cookie fix
            timeout=120000,
        )

        self.page = self.browser.new_page()
        self.page.set_default_navigation_timeout(60000)

        # Set large viewport to show more content without scrolling
        self.page.set_viewport_size({"width": 1920, "height": 1200})

        # Hide automation indicators (defense in depth)
        # Already handled by --disable-blink-features=AutomationControlled in args above
        self.page.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """
        )

        if force and had_previous_browser_state:
            return f"Previous browser closed by force. Browser opened with persistent profile: {profile_dir}"
        if had_previous_browser_state:
            return f"Previous stale browser state closed. Browser opened with persistent profile: {profile_dir}"
        return f"Browser opened with persistent profile: {profile_dir}"

    def go_to(self, url: str) -> str:
        """Navigate to a URL."""
        if not self.page:
            self.open_browser()

        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}' if '.' in url else f'http://{url}'

        self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
        self.page.wait_for_timeout(2000)
        self.current_url = self.page.url
        self._save_context()
        return f"Navigated to {self.current_url}"

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

    def click_element_by_selector(self, selector: str, index: int = 0, text: str = "") -> str:
        """Click an element using a CSS selector via Playwright locator().

        Use when a workflow has a stable selector such as an aria-label,
        role-compatible attribute, or data-testid. `index` is zero-based.
        If `text` is provided, only visible elements with exactly that text are
        considered.
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

        locator = self.page.locator(selector)
        count = locator.count()
        if count == 0:
            return f"No element found for selector: {selector}"
        if index < 0 or index >= count:
            return f"Selector matched {count} elements; index {index} is out of range"

        target = locator.nth(index)
        box = target.bounding_box()
        if box:
            self.page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        else:
            target.click(force=True)

        self._save_context()
        self.page.wait_for_timeout(1000)
        return f"Clicked element {index + 1}/{count} matching selector: {selector}"

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
        if not PLAYWRIGHT_AVAILABLE:
            return 'Browser tools not installed. Run: pip install playwright && playwright install chromium'

        if not self.page:
            return "Browser not open"

        os.makedirs(self.screenshots_dir, exist_ok=True)

        if not path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"step_{timestamp}.png"

        if not "/" in path:
            path = f"{self.screenshots_dir}/{path}"

        screenshot_bytes = self.page.screenshot(path=path, full_page=full_page)

        # Print where screenshot was saved
        print(f"\n[browser] Screenshot saved to: {path}")
        print(f"[browser] Full page: {full_page}, Size: {len(screenshot_bytes)} bytes\n")

        # Wait for page to stabilize after screenshot (especially for full_page which scrolls/resizes)
        # This prevents focus loss when typing after taking a screenshot
        self.page.wait_for_timeout(1000)

        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        return f"data:image/png;base64,{screenshot_base64}"

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

        Useful for sites with 2FA or CAPTCHA.

        Args:
            site_name: Name of the site (e.g., "Gmail")

        Returns:
            Confirmation when user is ready to continue
        """
        if not self.page:
            return "Browser not open"

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

    def close(self) -> str:
        """Close the browser and save persistent context."""
        cleanup_errors = []
        try:
            self._save_context()
        except Exception as exc:
            cleanup_errors.append(f"save context failed: {exc}")

        try:
            if self.page:
                self.page.close()
        except Exception as exc:
            cleanup_errors.append(f"close page failed: {exc}")
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

        self.page = None
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
