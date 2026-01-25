"""
Natural language browser automation via Playwright.

Architecture (inspired by browser-use):
1. element_finder.py extracts interactive elements with injected `data-browser-agent-id` attributes
2. LLM SELECTS from indexed element list, never GENERATES CSS selectors
3. Click/fill uses the injected attribute locator: [data-browser-agent-id="42"]
4. Coordinate-based clicking as fallback (fresh bounding box from locator)

Why this approach?
- LLMs generate invalid CSS like `:contains()` (jQuery, not CSS)
- Pre-built locators are guaranteed to work
- Injected IDs are unique and stable during the session

Usage:
    web = WebAutomation()
    web.open_browser()
    web.go_to("https://example.com")
    web.click("the submit button")  # LLM matches to element, clicks by coordinate

Dependencies: element_finder, highlight_screenshot, scroll, playwright, connectonion
Prompts: prompts/scroll_strategy.md, prompts/form_filler.md
State: maintains browser/page/current_url | screenshots auto-save to screenshots/
"""

from typing import Optional, List, Dict, Any, Literal
from pathlib import Path
from connectonion import xray, llm_do
from playwright.sync_api import sync_playwright, Page, Browser, Playwright
import base64
import json
import logging
from pydantic import BaseModel, Field
import scroll
import element_finder
import highlight_screenshot

# Load prompts from files
_BASE_DIR = Path(__file__).parent
_FORM_FILLER_PROMPT = (_BASE_DIR / "prompts" / "form_filler.md").read_text()

logger = logging.getLogger(__name__)


# Simple, clear data models
class FormField(BaseModel):
    """A form field on a web page."""
    name: str = Field(..., description="Field name or identifier")
    label: str = Field(..., description="User-facing label")
    type: str = Field(..., description="Input type (text, email, select, etc.)")
    value: Optional[str] = Field(None, description="Current value")
    required: bool = Field(False, description="Is this field required?")
    options: List[str] = Field(default_factory=list, description="Available options for select/radio")


class WebAutomation:
    """Web browser automation with form handling capabilities.

    Simple interface for complex web interactions.
    """

    def __init__(self, use_chrome_profile: bool = False):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.current_url: str = ""
        self.form_data: Dict[str, Any] = {}
        self.use_chrome_profile = use_chrome_profile

    def open_browser(self, headless: bool = False) -> str:
        """Open a new browser window.

        Note: If use_chrome_profile=True, Chrome must be completely closed before running.
        """
        if self.browser:
            return "Browser already open"

        import os
        from pathlib import Path

        self.playwright = sync_playwright().start()

        if self.use_chrome_profile:
            # Use Chromium with Chrome profile copy (avoids Chrome 136 restrictions)
            chromium_profile = Path.cwd() / ".browser_agent_profile"

            # If profile doesn't exist, copy it from user's Chrome
            if not chromium_profile.exists():
                import shutil

                # Determine source Chrome profile path
                home = Path.home()
                if os.name == 'nt':  # Windows
                    source_profile = home / "AppData/Local/Google/Chrome/User Data"
                elif os.uname().sysname == 'Darwin':  # macOS
                    source_profile = home / "Library/Application Support/Google/Chrome"
                else:  # Linux
                    source_profile = home / ".config/google-chrome"

                if source_profile.exists():
                    # Copy profile (exclude caches for speed)
                    shutil.copytree(
                        source_profile,
                        chromium_profile,
                        ignore=shutil.ignore_patterns('*Cache*', '*cache*', 'Service Worker', 'ShaderCache'),
                        dirs_exist_ok=True
                    )

            # Launch Chromium with persistent context using copied Chrome profile
            self.browser = self.playwright.chromium.launch_persistent_context(
                str(chromium_profile),
                headless=headless,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-blink-features=AutomationControlled',
                ],
                ignore_default_args=['--enable-automation'],
                timeout=120000,  # 120 seconds timeout
            )
            self.page = self.browser.pages[0] if self.browser.pages else self.browser.new_page()

            # Hide webdriver property
            self.page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            # Set default viewport to desktop size
            self.page.set_viewport_size({"width": 1920, "height": 1080})
            return f"Browser opened with Chromium using Chrome profile: {chromium_profile}"
        else:
            # Default behavior: launch without profile
            self.browser = self.playwright.chromium.launch(headless=headless)
            self.page = self.browser.new_page()
            # Set default viewport to desktop size
            self.page.set_viewport_size({"width": 1920, "height": 1080})
            return "Browser opened successfully"

    def go_to(self, url: str) -> str:
        """Navigate to a URL."""
        if not self.page:
            return "Browser not open. Call open_browser() first"

        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}' if '.' in url else f'http://{url}'

        self.page.goto(url, wait_until='domcontentloaded', timeout=60000)
        self.page.wait_for_timeout(2000)
        self.current_url = self.page.url
        return f"Navigated to {self.current_url}"

    def find_element_by_description(self, description: str) -> str:
        """Find an element on the page using natural language description.

        Uses the new dom_service architecture:
        1. Extracts all interactive elements with pre-built locators
        2. LLM SELECTS from options (by index), never generates CSS
        3. Returns the pre-built Playwright locator (guaranteed valid)

        Args:
            description: Natural language description of what you're looking for
                        e.g., "the submit button", "email input field", "Ryan Tan KK"

        Returns:
            Playwright locator string for the found element, or error message
        """
        if not self.page:
            return "Browser not open"

        # Use dom_service to match element (LLM selects, doesn't generate)
        element = element_finder.find_element(self.page, description)

        if element:
            return element.locator
        else:
            return f"Could not find element matching: {description}"

    def click(self, description: str) -> str:
        """Click on an element using natural language description.

        Uses dom_service: LLM selects from pre-built locators, never generates CSS.

        Args:
            description: Natural language description like "the blue submit button"
                        or "the email field" or "Ryan Tan KK"
        """
        if not self.page:
            return "Browser not open"

        # Use dom_service to match and click (LLM selects, doesn't generate)
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

            # If no bounding box, use force click
            locator.first.click(force=True)
            return f"Clicked [{element.index}] {element.tag} '{element.text}' (force)"

        # Fallback: use original coordinates
        x = element.x + element.width // 2
        y = element.y + element.height // 2
        self.page.mouse.click(x, y)
        return f"Clicked [{element.index}] '{element.text}' at ({x}, {y})"


    def type_text(self, field_description: str, text: str) -> str:
        """Type text into a form field using natural language description.

        Uses dom_service: LLM selects from pre-built locators, never generates CSS.

        Args:
            field_description: Natural language description of the field
                              e.g., "email field", "password input", "search box"
            text: The text to type into the field
        """
        if not self.page:
            return "Browser not open"

        # Use dom_service to match element (LLM selects, doesn't generate)
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

        text = self.page.inner_text("body")
        return text

    def set_viewport(self, width: int, height: int) -> str:
        """Set the browser viewport size."""
        if not self.page:
            return "Browser not open"
        self.page.set_viewport_size({"width": width, "height": height})
        return f"Viewport set to {width}x{height}"

    @xray
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
        if not self.page:
            return "Browser not open"

        import os
        from pathlib import Path
        from datetime import datetime

        # Navigate if URL provided
        if url:
            self.go_to(url)

        # Set viewport size
        self.page.set_viewport_size({"width": width, "height": height})

        # Create screenshots directory
        os.makedirs("screenshots", exist_ok=True)

        # Generate filename if needed
        if not path:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = f'screenshots/screenshot_{timestamp}.png'
        elif not path.startswith('/'):
            if not path.endswith(('.png', '.jpg', '.jpeg')):
                path += '.png'
            path = f'screenshots/{path}'
        elif not path.endswith(('.png', '.jpg', '.jpeg')):
            path += '.png'

        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        # Take screenshot
        self.page.screenshot(path=path, full_page=full_page)
        return f'Screenshot saved: {path}'

    def take_highlighted_screenshot(self) -> str:
        """Take a screenshot with all interactive elements highlighted.

        Shows colored bounding boxes around each element with index numbers.
        Useful for debugging which elements the agent can see.

        Returns:
            Path to the highlighted screenshot
        """
        if not self.page:
            return "Browser not open"

        return highlight_screenshot.highlight_current_page(self.page)

    def find_forms(self) -> List[FormField]:
        """Find all form fields on the current page."""
        if not self.page:
            return []

        # Get all form inputs using JavaScript
        fields_data = self.page.evaluate("""
            () => {
                const fields = [];
                const inputs = document.querySelectorAll('input, textarea, select');

                inputs.forEach(input => {
                    const label = input.labels?.[0]?.textContent ||
                                input.placeholder ||
                                input.name ||
                                input.id ||
                                'Unknown';

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

        # Try common submit buttons
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

        # Try pressing Enter in the last form field
        if self.form_data:
            last_field = list(self.form_data.keys())[-1]
            self.page.press(f"input[name='{last_field}']", "Enter")
            return "Form submitted with Enter key"

        return "Could not find submit button"

    def select_option(self, field_description: str, option: str) -> str:
        """Select an option from a dropdown using natural language.

        Args:
            field_description: Natural description of the dropdown
            option: The option text to select
        """
        if not self.page:
            return "Browser not open"

        selector = self.find_element_by_description(field_description)

        if selector.startswith("Could not"):
            return selector

        # Select the option
        self.page.select_option(selector, label=option)
        return f"Selected '{option}' in {field_description}"


    def check_checkbox(self, description: str, checked: bool = True) -> str:
        """Check or uncheck a checkbox using natural language.

        Args:
            description: Natural description of the checkbox
            checked: True to check, False to uncheck
        """
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
        """Wait for an element described in natural language to appear.

        Args:
            description: Natural language description of the element
            timeout: Maximum wait time in seconds
        """
        if not self.page:
            return "Browser not open"

        # Find the selector first
        selector = self.find_element_by_description(description)

        if selector.startswith("Could not"):
            # Try waiting for text instead
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

    def extract_data(self, selector: str) -> List[str]:
        """Extract data from elements matching a selector."""
        if not self.page:
            return []

        elements = self.page.locator(selector)
        count = elements.count()

        data = []
        for i in range(count):
            text = elements.nth(i).inner_text()
            data.append(text)

        return data

    @xray
    def scroll(self, times: int = 5, description: str = "the main content area") -> str:
        """Universal scroll with AI strategy and fallback.

        Tries: AI-generated → Element scroll → Page scroll
        Verifies success with screenshot comparison.
        """
        return scroll.scroll(self.page, self.take_screenshot, times, description)

    def wait_for_manual_login(self, site_name: str = "the website") -> str:
        """Pause automation and wait for user to login manually.

        Args:
            site_name: Name of the site user needs to login to (e.g., "Gmail")

        Returns:
            Confirmation message when user is ready to continue
        """
        if not self.page:
            return "Browser not open"

        print(f"\n{'='*60}")
        print(f"⏸️  MANUAL LOGIN REQUIRED")
        print(f"{'='*60}")
        print(f"Please login to {site_name} in the browser window.")
        print(f"Once you're logged in and ready to continue:")
        print(f"  Type 'yes' or 'Y' and press Enter")
        print(f"{'='*60}\n")

        while True:
            response = input("Ready to continue? (yes/Y): ").strip().lower()
            if response in ['yes', 'y']:
                print("✅ Continuing automation...\n")
                return f"User confirmed login to {site_name} - continuing automation"
            else:
                print("Please type 'yes' or 'Y' when ready.")

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


# Standalone helper functions for AI-powered analysis
def analyze_page(html_content: str, question: str) -> str:
    """Ask a question about page content using AI."""
    return llm_do(
        f"Based on this HTML content, {question}\n\n {html_content}",
        model="co/gemini-2.5-flash",
        temperature=0.3
    )


def smart_fill_form(fields: List[FormField], user_info: str) -> Dict[str, str]:
    """Generate smart form values based on user information."""

    class FormData(BaseModel):
        values: Dict[str, str]

    field_descriptions = "\n".join([
        f"- {f.name}: {f.label} ({f.type}, required: {f.required})"
        for f in fields
    ])

    prompt = _FORM_FILLER_PROMPT.format(
        user_info=user_info,
        field_descriptions=field_descriptions
    )
    result = llm_do(
        prompt,
        output=FormData,
        model="co/gemini-2.5-flash",
        temperature=0.7
    )

    return result.values