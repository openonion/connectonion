"""
Purpose: Natural language browser automation via Playwright with persistent profile and auto-save
LLM-Note:
  Dependencies: imports from [playwright.sync_api, connectonion Agent/llm_do, cli/browser_agent/element_finder, pydantic, pathlib, dotenv] | imported by [cli/commands/browser_commands.py] | tested by [tests/cli/test_browser_agent.py]
  Data flow: BrowserAutomation() initializes Playwright → opens browser with persistent context → provides tools (navigate, find_element, click, type_text, screenshot, scroll, wait_for_login) → auto-saves cookies after each critical action → Agent uses these tools via natural language → element_finder.py uses vision LLM to locate elements | screenshots saved to .tmp/ directory
  State/Effects: maintains browser/page/context state | persistent profile at ~/.co/browser_profile/ | auto-saves cookies after navigation and manual login | writes screenshots to .tmp/{timestamp}.png | modifies form_data dict for form fills | context manager ensures cleanup
  Integration: exposes BrowserAutomation(use_chrome_profile, headless) with methods: navigate(url), find_element(description), screenshot(viewport), scroll(direction, description), click(description), keyboard_type(text), wait_for_login(seconds) | used by `co browser` CLI command
  Performance: headless by default (faster) | persistent context (instant profile load) | vision model for element finding (slower but accurate) | screenshots base64-encoded for LLM analysis | auto-save adds 500ms delay after critical actions
  Errors: returns error string if Playwright not installed | returns "Browser already open" if reinitializing | element not found returns descriptive error
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
PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "agent.md"


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

    def __init__(self, use_chrome_profile: bool = True, headless: bool = True):
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
        # Auto-initialize browser so it's ready immediately
        self._initialize_browser()

    def _initialize_browser(self):
        """Initialize the browser instance on startup."""
        if not PLAYWRIGHT_AVAILABLE:
            return
        self.open_browser(headless=self._headless)

    def open_browser(self, headless: bool = True) -> str:
        """Open a new browser window.

        Args:
            headless: If True, browser runs without visible window.

        Note: If use_chrome_profile=True, Chrome must be completely closed.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "Browser tools not installed. Run: pip install playwright && playwright install chromium"

        if self.browser:
            return "Browser already open"

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

    def click(self, description: str) -> str:
        """Click on an element using natural language description.

        Uses element_finder: LLM selects from pre-built locators, never generates CSS.
        """
        if not self.page:
            return "Browser not open"

        element = element_finder.find_element(self.page, description)

        if not element:
            # Fallback to simple text matching
            text_locator = self.page.get_by_text(description)
            if text_locator.count() > 0:
                text_locator.first.click()
                self._save_context()
                return f"Clicked on '{description}' (by text fallback)"
            return f"Could not find element matching: {description}"

        # Try the locator with fresh bounding box
        locator = self.page.locator(element.locator)

        if locator.count() > 0:
            box = locator.first.bounding_box()
            if box:
                x = box['x'] + box['width'] / 2
                y = box['y'] + box['height'] / 2
                self.page.mouse.click(x, y)
                self._save_context()
                return f"Clicked [{element.index}] {element.tag} '{element.text}'"

            locator.first.click(force=True)
            self._save_context()
            return f"Clicked [{element.index}] {element.tag} '{element.text}' (force)"

        # Fallback: use original coordinates
        x = element.x + element.width // 2
        y = element.y + element.height // 2
        self.page.mouse.click(x, y)
        self._save_context()
        return f"Clicked [{element.index}] '{element.text}' at ({x}, {y})"

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


    def get_text(self) -> str:
        """Get all visible text from the page."""
        if not self.page:
            return "Browser not open"
        return self.page.inner_text("body")

    def get_current_url(self) -> str:
        """Get the current page URL."""
        if not self.page:
            return "Browser not open"
        return self.page.url

    def take_screenshot(self, path: str = None, full_page: bool = False) -> str:
        """Take a screenshot of the current page and return base64 encoded image.

        Args:
            path: Optional path for the screenshot
            full_page: If True, captures entire page height (may lose details but shows overview)

        Returns:
            Base64 encoded image data with system reminder for full-page screenshots
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

        # Wait for page to stabilize after screenshot (especially for full_page which scrolls/resizes)
        # This prevents focus loss when typing after taking a screenshot
        self.page.wait_for_timeout(1000)

        screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

        if full_page:
            return f"""data:image/png;base64,{screenshot_base64}

SYSTEM REMINDER: Full-page screenshots provide an overview of the entire page but may not show details clearly. Some elements might not be loaded yet (lazy loading). If you need to verify specific content or see details clearly, consider: scroll() to the target area first, then take a regular screenshot (full_page=False), or use scroll() multiple times and take screenshots at each position."""
        else:
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
        self._save_context()

        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

        self.page = None
        self.browser = None
        self.playwright = None
        return "Browser closed"

    def __enter__(self):
        """Context manager entry - browser already initialized in __init__."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures browser closes and saves context."""
        self.close()
        return False


def execute_browser_command(command: str, headless: bool = True) -> str:
    """Execute a browser command using natural language.

    Returns the agent's natural language response directly.
    """
    api_key = os.getenv('OPENONION_API_KEY')

    if not api_key:
        global_env = Path.home() / ".co" / "keys.env"
        if global_env.exists():
            load_dotenv(global_env)
            api_key = os.getenv('OPENONION_API_KEY')

    if not api_key:
        return 'Browser agent requires authentication. Run: co auth'

    with BrowserAutomation(headless=headless) as browser:
        agent = Agent(
            name="browser_cli",
            model="co/gemini-3-flash-preview",
            api_key=api_key,
            system_prompt=PROMPT_PATH,
            tools=[browser],
            plugins=[image_result_formatter, ui_stream],
            max_iterations=200
        )
        return agent.input(command)
