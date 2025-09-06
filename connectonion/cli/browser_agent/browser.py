"""Browser Agent for CLI - Natural language browser automation.

This module provides a browser automation agent that understands natural language
requests for taking screenshots and other browser operations via the ConnectOnion CLI.
"""

import os
from pathlib import Path
from datetime import datetime
from connectonion import Agent, llm_do
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
load_dotenv()

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
        self._current_page = None
        self._browser = None
    
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
        
        # Normalize URL
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}' if '.' in url else f'http://{url}'
        
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": width, "height": height})
            page.goto(url, wait_until='networkidle', timeout=30000)
            page.screenshot(path=path, full_page=full_page)
            browser.close()
        
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
    
    def get_page_html(self, url: str) -> str:
        """Get the HTML content of a webpage.
        
        Args:
            url: The URL to get HTML from
            
        Returns:
            The HTML content of the page
        """
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}' if '.' in url else f'http://{url}'
        
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle', timeout=30000)
            html_content = page.content()
            browser.close()
        
        return html_content
    
    def click_element(self, url: str, description: str) -> str:
        """Click an element on a webpage based on natural language description.
        
        Args:
            url: The URL of the page
            description: Natural language description of what to click
            
        Returns:
            Result message
        """
        if not url.startswith(('http://', 'https://')):
            url = f'https://{url}' if '.' in url else f'http://{url}'
        
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until='networkidle', timeout=30000)
            html_content = page.content()
            
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
                page.get_by_text(result.selector).click()
            else:
                page.locator(result.selector).click()
            
            page.wait_for_timeout(1000)
            browser.close()
            return f"Clicked: {result.selector}"


# Removed create_browser_agent to reduce indirection; agent is constructed inline


# Removed thin wrapper to reduce indirection


def execute_browser_command(command: str) -> str:
    """Execute a browser command using natural language.

    Returns the agent's natural language response directly.
    """
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key or api_key == 'sk-your-key-here':
        return '❌ Natural language browser agent unavailable. Set OPENAI_API_KEY and try again.'

    browser = BrowserAutomation()
    agent = Agent(
        name="browser_cli",
        system_prompt=PROMPT_PATH,
        tools=[browser],
        max_iterations=10
    )
    return agent.input(command)

