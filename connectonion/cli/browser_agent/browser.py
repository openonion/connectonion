"""Browser Agent for CLI - Natural language browser automation.

This module provides a browser automation agent that understands natural language
requests for taking screenshots and other browser operations via the ConnectOnion CLI.
"""

import os
from pathlib import Path
from datetime import datetime
from connectonion import Agent, llm_do, xray
from dotenv import load_dotenv
from pydantic import BaseModel

# Default screenshots directory in current working directory
SCREENSHOTS_DIR = Path.cwd() / ".tmp"

# Check Playwright availability
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Path to the browser agent system prompt
PROMPT_PATH = Path(__file__).parent / "prompt.md"


class BrowserAutomation:
    """Browser automation for screenshots and interactions."""
    
    def __init__(self):
        self._screenshots = []
        self._playwright = None
        self._browser = None
        self._page = None
        self._initialize_browser()
    
    def _initialize_browser(self):
        """Initialize the browser instance."""
        if not PLAYWRIGHT_AVAILABLE:
            return
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._page = self._browser.new_page()
    
    def navigate_to(self, url: str) -> str:
        """Navigate to a URL."""
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}' if '.' in url else f'http://{url}'
        self._page.goto(url, wait_until='networkidle', timeout=30000)
        # Sleep for 2 seconds to ensure page is fully loaded
        self._page.wait_for_timeout(2000)
        return f"Navigated to {url}"
    
    def set_viewport(self, width: int, height: int) -> str:
        """Set the browser viewport size.
        
        Args:
            width: Viewport width in pixels
            height: Viewport height in pixels
            
        Returns:
            Success message
        """
        if not PLAYWRIGHT_AVAILABLE:
            return 'Browser tools not installed. Run: pip install playwright && playwright install chromium'
        self._page.set_viewport_size({"width": width, "height": height})
        return f"Viewport set to {width}x{height}"
    
    def take_screenshot(self, url: str, path: str = "", 
                       width: int = 1920, height: int = 1080,
                       full_page: bool = False) -> str:
        """Take a screenshot of the specified URL.
        
        Args:
            url: The URL to screenshot (e.g., "localhost:3000", "example.com")
            path: Optional path to save the screenshot (auto-generates if empty)
            width: Viewport width in pixels (default 1920)
            height: Viewport height in pixels (default 1080)
            full_page: If True, captures entire page height
            
        Returns:
            Success or error message
        """
        if not PLAYWRIGHT_AVAILABLE:
            return 'Browser tools not installed. Run: pip install playwright && playwright install chromium'
        
        # Navigate to URL
        self.navigate_to(url)
        
        # Set viewport size
        self._page.set_viewport_size({"width": width, "height": height})
        
        # Generate filename if needed
        if not path:
            # Ensure screenshots directory exists
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            path = str(SCREENSHOTS_DIR / f'screenshot_{timestamp}.png')
        elif not path.startswith('/'):  # Relative path
            # If relative path given, save to screenshots dir
            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            if not path.endswith(('.png', '.jpg', '.jpeg')):
                path += '.png'
            path = str(SCREENSHOTS_DIR / path)
        elif not path.endswith(('.png', '.jpg', '.jpeg')):
            # Absolute path without extension
            path += '.png'
        
        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        # Take screenshot
        self._page.screenshot(path=path, full_page=full_page)
        
        self._screenshots.append(path)
        return f'Screenshot saved: {path}'
    
    def screenshot_with_iphone_viewport(self, url: str, path: str = "") -> str:
        """Take a screenshot with iPhone viewport (390x844)."""
        return self.take_screenshot(url, path, width=390, height=844)
    
    def screenshot_with_ipad_viewport(self, url: str, path: str = "") -> str:
        """Take a screenshot with iPad viewport (768x1024)."""
        return self.take_screenshot(url, path, width=768, height=1024)
    
    def screenshot_with_desktop_viewport(self, url: str, path: str = "") -> str:
        """Take a screenshot with desktop viewport (1920x1080)."""
        return self.take_screenshot(url, path, width=1920, height=1080)
    
    def get_current_page_html(self) -> str:
        """Get the HTML content of the current page.
        
        Returns:
            The HTML content of the current page
        """
        if not PLAYWRIGHT_AVAILABLE:
            return 'Browser tools not installed. Run: pip install playwright && playwright install chromium'
        return self._page.content()
    
    def get_current_url(self) -> str:
        """Get the current page URL.
        
        Returns:
            The current URL
        """
        if not PLAYWRIGHT_AVAILABLE:
            return 'Browser tools not installed. Run: pip install playwright && playwright install chromium'
        return self._page.url
    
    def wait(self, seconds: float) -> str:
        """Wait for a specified number of seconds.
        
        Args:
            seconds: Number of seconds to wait
            
        Returns:
            Success message
        """
        if not PLAYWRIGHT_AVAILABLE:
            return 'Browser tools not installed. Run: pip install playwright && playwright install chromium'
        self._page.wait_for_timeout(seconds * 1000)  # Convert to milliseconds
        return f"Waited for {seconds} seconds"
    
    @xray
    def get_debug_trace(self) -> str:
        """Get execution trace for debugging.
        
        Returns:
            Execution trace showing what happened
        """
        if hasattr(xray, 'trace'):
            return xray.trace()
        return "No trace available"
    
    def click_element_by_description(self, description: str) -> str:
        """Click an element on the current page based on natural language description.
        
        Args:
            description: Natural language description of what to click
            
        Returns:
            Result message
        """
        if not PLAYWRIGHT_AVAILABLE:
            return 'Browser tools not installed. Run: pip install playwright && playwright install chromium'
        
        html_content = self._page.content()
        
        # Use llm_do to determine the selector
        class ElementSelector(BaseModel):
            selector: str
            method: str  # "text" or "css"
        
        result = llm_do(
            f"Find selector for: {description}\n\nHTML:\n{html_content[:5000]}",
            output=ElementSelector,
            system_prompt="Return the best selector to click the element. Use method='text' for button text, method='css' for CSS selectors."
        )
        
        if result.method == "text":
            self._page.get_by_text(result.selector).click()
        else:
            self._page.locator(result.selector).click()
        
        self._page.wait_for_timeout(1000)
        return f"Clicked: {result.selector}"





def execute_browser_command(command: str) -> str:
    """Execute a browser command using natural language.

    Returns the agent's natural language response directly.
    """
    # Framework auto-loads local .env, but CLI commands need global fallback
    # Check for API key in environment first
    api_key = os.getenv('OPENONION_API_KEY')

    # If not found, try loading from global config
    if not api_key:
        global_env = Path.home() / ".co" / "keys.env"
        if global_env.exists():
            load_dotenv(global_env)
            api_key = os.getenv('OPENONION_API_KEY')

    if not api_key:
        return '❌ Browser agent requires authentication. Run: co auth'

    browser = BrowserAutomation()
    agent = Agent(
        name="browser_cli",
        model="co/o4-mini",
        api_key=api_key,
        system_prompt=PROMPT_PATH,
        tools=[browser],
        max_iterations=10
    )
    return agent.input(command)

