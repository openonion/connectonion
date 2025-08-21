#!/usr/bin/env python3
"""
Real-World Example: Playwright Web Automation with ConnectOnion

This example shows how to use stateful tools for real web automation
using Playwright. The browser state is shared between all tool calls.

Install dependencies:
    pip install playwright
    playwright install
"""

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  Playwright not installed. Run: pip install playwright && playwright install")

from connectonion import Agent


class BrowserAutomation:
    """Real browser automation tools with shared state."""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.screenshots = []
        self.visited_urls = []
    
    def start_browser(self, headless: bool = True) -> str:
        """Start a browser instance."""
        if not PLAYWRIGHT_AVAILABLE:
            return "Error: Playwright not installed"
        
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.page = self.browser.new_page()
        return f"Browser started (headless={headless})"
    
    def navigate(self, url: str) -> str:
        """Navigate to a URL."""
        if not self.page:
            return "Error: Browser not started. Call start_browser() first."
        
        self.page.goto(url)
        self.visited_urls.append(url)
        return f"Navigated to {url}"
    
    def get_title(self) -> str:
        """Get the current page title."""
        if not self.page:
            return "Error: No page loaded"
        
        title = self.page.title()
        return f"Page title: {title}"
    
    def take_screenshot(self, filename: str = None) -> str:
        """Take a screenshot of the current page."""
        if not self.page:
            return "Error: No page loaded"
        
        if not filename:
            filename = f"screenshot_{len(self.screenshots) + 1}.png"
        
        self.page.screenshot(path=filename)
        self.screenshots.append(filename)
        return f"Screenshot saved as {filename}"
    
    def click_element(self, selector: str) -> str:
        """Click an element by CSS selector."""
        if not self.page:
            return "Error: No page loaded"
        
        try:
            self.page.click(selector)
            return f"Clicked element: {selector}"
        except Exception as e:
            return f"Error clicking {selector}: {e}"
    
    def fill_input(self, selector: str, text: str) -> str:
        """Fill an input field."""
        if not self.page:
            return "Error: No page loaded"
        
        try:
            self.page.fill(selector, text)
            return f"Filled '{selector}' with '{text}'"
        except Exception as e:
            return f"Error filling {selector}: {e}"
    
    def get_text(self, selector: str) -> str:
        """Get text content of an element."""
        if not self.page:
            return "Error: No page loaded"
        
        try:
            text = self.page.text_content(selector)
            return f"Text content: {text}"
        except Exception as e:
            return f"Error getting text from {selector}: {e}"
    
    def wait_for_element(self, selector: str, timeout: int = 5000) -> str:
        """Wait for an element to appear."""
        if not self.page:
            return "Error: No page loaded"
        
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return f"Element {selector} appeared"
        except Exception as e:
            return f"Element {selector} did not appear: {e}"
    
    def get_session_info(self) -> str:
        """Get information about the current browser session."""
        if not self.browser:
            return "No browser session active"
        
        info = {
            "browser_running": self.browser is not None,
            "current_url": self.page.url if self.page else None,
            "visited_urls": self.visited_urls,
            "screenshots_taken": len(self.screenshots),
            "screenshot_files": self.screenshots
        }
        
        return f"Session info: {info}"
    
    def cleanup(self):
        """Clean up browser resources."""
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        
        print("🧹 Browser resources cleaned up!")


def demo_google_search():
    """Demonstrate automated Google search."""
    if not PLAYWRIGHT_AVAILABLE:
        print("Skipping Playwright demo - not installed")
        return
    
    print("=== Google Search Demo ===")
    
    # Create browser automation instance
    browser = BrowserAutomation()
    
    # Create agent with browser tools
    agent = Agent(
        name="search_agent",
        tools=browser,
        system_prompt="""You are a web automation assistant. 
        Help users navigate websites, search for information, and take screenshots.
        Always be step-by-step and describe what you're doing.""",
        max_iterations=15,  # Browser automation often needs more iterations
        api_key="demo_key"  # Replace with real key for actual LLM usage
    )
    
    print(f"Agent has {len(agent.tools)} browser tools available:")
    for tool_name in agent.tool_map.keys():
        print(f"  - {tool_name}")
    
    try:
        # Simulate agent workflow (in real usage, the LLM would call these)
        print("\n--- Simulating Automated Google Search ---")
        
        # Start browser
        result = agent.tool_map['start_browser'](headless=True)
        print(f"1. {result}")
        
        # Navigate to Google
        result = agent.tool_map['navigate'](url="https://www.google.com")
        print(f"2. {result}")
        
        # Get page title
        result = agent.tool_map['get_title']()
        print(f"3. {result}")
        
        # Take screenshot
        result = agent.tool_map['take_screenshot'](filename="google_homepage.png")
        print(f"4. {result}")
        
        # Fill search box (Google's search input)
        result = agent.tool_map['fill_input'](selector="textarea[name='q']", text="ConnectOnion Python")
        print(f"5. {result}")
        
        # Submit search
        result = agent.tool_map['click_element'](selector="input[name='btnK']")
        print(f"6. {result}")
        
        # Wait for results
        result = agent.tool_map['wait_for_element'](selector="#search", timeout=5000)
        print(f"7. {result}")
        
        # Take screenshot of results
        result = agent.tool_map['take_screenshot'](filename="search_results.png")
        print(f"8. {result}")
        
        # Get session info
        result = agent.tool_map['get_session_info']()
        print(f"9. {result}")
        
        print("\n--- User Has Full Access to Browser State ---")
        print(f"Current URL: {browser.page.url if browser.page else 'None'}")
        print(f"Screenshots taken: {browser.screenshots}")
        print(f"URLs visited: {browser.visited_urls}")
        
    except Exception as e:
        print(f"Demo error: {e}")
    
    finally:
        # Clean up
        browser.cleanup()


def demo_with_real_llm():
    """Example of how to use with real LLM (requires API key)."""
    if not PLAYWRIGHT_AVAILABLE:
        print("Skipping real LLM demo - Playwright not installed")
        return
    
    import os
    
    # Check if API key is available
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("To run with real LLM, set OPENAI_API_KEY environment variable")
        return
    
    print("=== Real LLM Demo ===")
    
    browser = BrowserAutomation()
    
    # Create agent with real API key
    agent = Agent(
        name="web_assistant",
        tools=browser,
        system_prompt="""You are a web automation expert. 
        Help users navigate websites efficiently. Always start the browser first.
        Take screenshots when you reach important pages.
        Be descriptive about what you see and do.""",
        max_iterations=20,  # Web automation may need many steps
        api_key=api_key
    )
    
    try:
        # This would actually call the LLM!
        result = agent.input("""
            Go to Wikipedia, search for 'Artificial Intelligence', 
            and take a screenshot of the main article page.
        """)
        
        print("LLM Result:", result)
        print(f"Screenshots: {browser.screenshots}")
        print(f"Current URL: {browser.page.url if browser.page else 'None'}")
        
    finally:
        browser.cleanup()


if __name__ == "__main__":
    demo_google_search()
    
    print("\n" + "="*50)
    print("💡 Key Benefits of Stateful Tools:")
    print("✅ Browser state persists across tool calls")
    print("✅ No need to pass browser object between functions")
    print("✅ User has full control over browser instance")
    print("✅ Easy to add new browser automation methods")
    print("✅ Clean resource management with manual cleanup")
    
    # Uncomment to test with real LLM (requires API key)
    # demo_with_real_llm()