"""Browser Agent for CLI - Natural language browser automation.

This module provides a browser automation agent that understands natural language
requests for browser operations via the ConnectOnion CLI.

Features:
- Chrome profile support for persistent sessions (cookies, logins)
- AI-powered element finding using natural language
- Form handling: find, fill, submit
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
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from . import element_finder

# Default screenshots directory
SCREENSHOTS_DIR = Path.cwd() / ".tmp"

# Check Playwright availability
try:
    from playwright.sync_api import sync_playwright, Page, Browser, Playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Path to the browser agent system prompt
PROMPT_PATH = Path(__file__).parent / "prompt.md"


class FormField(BaseModel):
    """A form field on a web page."""
    name: str = Field(..., description="Field name or identifier")
    label: str = Field(..., description="User-facing label")
    type: str = Field(..., description="Input type (text, email, select, etc.)")
    value: Optional[str] = Field(None, description="Current value")
    required: bool = Field(False, description="Is this field required?")
    options: List[str] = Field(default_factory=list, description="Available options for select/radio")


class BrowserAutomation:
    """Browser automation with natural language support.

    Simple interface for complex web interactions.
    Auto-initializes browser on creation for immediate use.
    Supports Chrome profile for persistent sessions.
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

        if self.use_chrome_profile:
            # Use Chromium with Chrome profile copy
            chromium_profile = Path.cwd() / "chromium_automation_profile"

            if not chromium_profile.exists():
                import shutil
                home = Path.home()
                if os.name == 'nt':  # Windows
                    source_profile = home / "AppData/Local/Google/Chrome/User Data"
                elif os.uname().sysname == 'Darwin':  # macOS
                    source_profile = home / "Library/Application Support/Google/Chrome"
                else:  # Linux
                    source_profile = home / ".config/google-chrome"

                if source_profile.exists():
                    def safe_copy(src, dst):
                        try:
                            shutil.copy2(src, dst)
                        except:
                            pass  # Skip any file that can't be copied

                    shutil.copytree(
                        source_profile,
                        chromium_profile,
                        ignore=shutil.ignore_patterns(
                            '*Cache*', '*cache*', 'Service Worker', 'ShaderCache',
                            'Singleton*', '*lock*', '*Lock*', '*.tmp', 'GPUCache',
                            'Code Cache', 'DawnCache', 'GrShaderCache', 'blob_storage'
                        ),
                        copy_function=safe_copy,
                        dirs_exist_ok=True
                    )

            self.browser = self.playwright.chromium.launch_persistent_context(
                str(chromium_profile),
                headless=headless,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-blink-features=AutomationControlled'],
                ignore_default_args=['--enable-automation'],
                timeout=120000,
            )
            self.page = self.browser.pages[0] if self.browser.pages else self.browser.new_page()
            self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            """)
            self.page.set_viewport_size({"width": 1920, "height": 1080})
            return f"Browser opened with Chrome profile: {chromium_profile}"
        else:
            self.browser = self.playwright.chromium.launch(headless=headless)
            self.page = self.browser.new_page()
            self.page.set_viewport_size({"width": 1920, "height": 1080})
            return "Browser opened successfully"

    def go_to(self, url: str) -> str:
        """Navigate to a URL."""
        if not self.page:
            self.open_browser()

        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}' if '.' in url else f'http://{url}'

        self.page.goto(url, wait_until='networkidle', timeout=30000)
        self.page.wait_for_timeout(2000)
        self.current_url = self.page.url
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
                return f"Clicked [{element.index}] {element.tag} '{element.text}'"

            locator.first.click(force=True)
            return f"Clicked [{element.index}] {element.tag} '{element.text}' (force)"

        # Fallback: use original coordinates
        x = element.x + element.width // 2
        y = element.y + element.height // 2
        self.page.mouse.click(x, y)
        return f"Clicked [{element.index}] '{element.text}' at ({x}, {y})"

    def type_text(self, field_description: str, text: str) -> str:
        """Type text into a form field.

        Uses element_finder: LLM selects from pre-built locators, never generates CSS.
        """
        if not self.page:
            return "Browser not open"

        element = element_finder.find_element(self.page, field_description)

        if not element:
            # Fallback to placeholder matching
            placeholder_locator = self.page.get_by_placeholder(field_description)
            if placeholder_locator.count() > 0:
                placeholder_locator.first.fill(text)
                self.form_data[field_description] = text
                return f"Typed into '{field_description}'"
            return f"Could not find field: {field_description}"

        # Try the pre-built locator
        locator = self.page.locator(element.locator)

        if locator.count() > 0:
            locator.first.fill(text)
            self.form_data[field_description] = text
            return f"Typed into [{element.index}] {element.tag}"

        # Fallback: click then type
        x = element.x + element.width // 2
        y = element.y + element.height // 2
        self.page.mouse.click(x, y)
        self.page.keyboard.type(text)
        self.form_data[field_description] = text
        return f"Typed into [{element.index}] at ({x}, {y})"

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

    def get_current_page_html(self) -> str:
        """Get the HTML content of the current page."""
        if not self.page:
            return "Browser not open"
        return self.page.content()

    def take_screenshot(self, url: str = None, path: str = "",
                       width: int = 1920, height: int = 1080,
                       full_page: bool = False) -> str:
        """Take a screenshot of a URL or current page.

        Args:
            url: URL to screenshot (optional - uses current page if not provided)
            path: Optional path to save (auto-generates if empty)
            width: Viewport width in pixels (default 1920)
            height: Viewport height in pixels (default 1080)
            full_page: If True, captures entire page height

        Returns:
            Path to saved screenshot
        """
        if not PLAYWRIGHT_AVAILABLE:
            return 'Browser tools not installed. Run: pip install playwright && playwright install chromium'

        if not self.page:
            return "Browser not open"

        # Navigate if URL provided
        if url:
            self.go_to(url)

        # Set viewport size
        self.page.set_viewport_size({"width": width, "height": height})

        # Generate filename if needed
        if not path:
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = str(SCREENSHOTS_DIR / f'screenshot_{timestamp}.png')
        elif not path.startswith('/'):
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            if not path.endswith(('.png', '.jpg', '.jpeg')):
                path += '.png'
            path = str(SCREENSHOTS_DIR / path)
        elif not path.endswith(('.png', '.jpg', '.jpeg')):
            path += '.png'

        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        # Take screenshot
        self.page.screenshot(path=path, full_page=full_page)
        self._screenshots.append(path)
        return f'Screenshot saved: {path}'

    def set_viewport(self, width: int, height: int) -> str:
        """Set the browser viewport size."""
        if not self.page:
            return "Browser not open"
        self.page.set_viewport_size({"width": width, "height": height})
        return f"Viewport set to {width}x{height}"

    def find_forms(self) -> List[FormField]:
        """Find all form fields on the current page."""
        if not self.page:
            return []

        fields_data = self.page.evaluate("""
            () => {
                const fields = [];
                document.querySelectorAll('input, textarea, select').forEach(input => {
                    const label = input.labels?.[0]?.textContent ||
                                input.placeholder || input.name || input.id || 'Unknown';
                    fields.push({
                        name: input.name || input.id || label,
                        label: label.trim(),
                        type: input.type || input.tagName.toLowerCase(),
                        value: input.value || '',
                        required: input.required || false,
                        options: input.tagName === 'SELECT' ?
                                Array.from(input.options).map(o => o.text) : []
                    });
                });
                return fields;
            }
        """)
        return [FormField(**field) for field in fields_data]

    def fill_form(self, data: Dict[str, str]) -> str:
        """Fill multiple form fields at once."""
        if not self.page:
            return "Browser not open"

        results = []
        for field_name, value in data.items():
            result = self.type_text(field_name, value)
            results.append(f"{field_name}: {result}")
        return "\n".join(results)

    def submit_form(self) -> str:
        """Submit the current form."""
        if not self.page:
            return "Browser not open"

        for selector in [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit')",
            "button:has-text('Send')",
            "button:has-text('Continue')",
            "button:has-text('Next')"
        ]:
            if self.page.locator(selector).count() > 0:
                self.page.click(selector)
                return "Form submitted"

        return "Could not find submit button"

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
        return scroll.scroll(self.page, self.take_screenshot, times, description)

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

    def close(self) -> str:
        """Close the browser."""
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


def execute_browser_command(command: str) -> str:
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

    browser = BrowserAutomation()
    agent = Agent(
        name="browser_cli",
        model="co/gemini-2.5-pro",
        api_key=api_key,
        system_prompt=PROMPT_PATH,
        tools=[browser],
        max_iterations=20
    )
    return agent.input(command)
