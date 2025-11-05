"""Playwright Web Automation Agent - Browser control and web scraping

Based on the ConnectOnion Playwright example with stateful browser tools.
"""

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️  Playwright not installed. Run: pip install playwright && playwright install")

from connectonion import Agent, xray
from typing import Optional, List, Dict
import json


class BrowserAutomation:
    """Stateful browser automation tools with shared browser instance."""
    
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.page = None
        self.screenshots = []
        self.visited_urls = []
        self.downloads = []
    
    @xray
    def start_browser(self, headless: bool = True) -> str:
        """Start a browser instance.
        
        Args:
            headless: Run browser in headless mode (no UI)
        """
        if not PLAYWRIGHT_AVAILABLE:
            return "Error: Playwright not installed. Run: pip install playwright && playwright install"
        
        if self.browser:
            return "Browser already running"
        
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.page = self.browser.new_page()
        return f"✅ Browser started (headless={headless})"
    
    @xray
    def navigate(self, url: str, wait_until: str = "load") -> str:
        """Navigate to a URL.
        
        Args:
            url: The URL to navigate to
            wait_until: When to consider navigation done ('load', 'domcontentloaded', 'networkidle')
        """
        if not self.page:
            return "❌ Browser not started. Call start_browser() first."
        
        try:
            self.page.goto(url, wait_until=wait_until)
            self.visited_urls.append(url)
            title = self.page.title()
            return f"✅ Navigated to {url}\nPage title: {title}"
        except Exception as e:
            return f"❌ Navigation failed: {e}"
    
    @xray
    def take_screenshot(self, filename: str = None, full_page: bool = False) -> str:
        """Take a screenshot of the current page.
        
        Args:
            filename: Name for the screenshot file
            full_page: Capture full scrollable page
        """
        if not self.page:
            return "❌ No page loaded"
        
        if not filename:
            filename = f"screenshot_{len(self.screenshots) + 1}.png"
        
        try:
            self.page.screenshot(path=filename, full_page=full_page)
            self.screenshots.append(filename)
            return f"📸 Screenshot saved as {filename}"
        except Exception as e:
            return f"❌ Screenshot failed: {e}"
    
    @xray
    def scrape_content(self, selector: str = "body") -> str:
        """Extract text content from the page.
        
        Args:
            selector: CSS selector for the element to scrape
        """
        if not self.page:
            return "❌ No page loaded"
        
        try:
            element = self.page.query_selector(selector)
            if element:
                text = element.inner_text()
                return f"📄 Content from {selector}:\n{text[:500]}..." if len(text) > 500 else f"📄 Content from {selector}:\n{text}"
            else:
                return f"❌ No element found matching selector: {selector}"
        except Exception as e:
            return f"❌ Scraping failed: {e}"
    
    @xray
    def fill_form(self, form_data: str) -> str:
        """Fill form fields on the page.
        
        Args:
            form_data: JSON string with selector-value pairs, e.g., '{"#name": "John", "#email": "john@example.com"}'
        """
        if not self.page:
            return "❌ No page loaded"
        
        try:
            data = json.loads(form_data)
            filled = []
            
            for selector, value in data.items():
                self.page.fill(selector, str(value))
                filled.append(f"{selector} = {value}")
            
            return f"✅ Form filled:\n" + "\n".join(filled)
        except json.JSONDecodeError:
            return "❌ Invalid JSON format for form_data"
        except Exception as e:
            return f"❌ Form filling failed: {e}"
    
    @xray
    def click(self, selector: str) -> str:
        """Click an element on the page.
        
        Args:
            selector: CSS selector for the element to click
        """
        if not self.page:
            return "❌ No page loaded"
        
        try:
            self.page.click(selector)
            # Wait a bit for any navigation
            self.page.wait_for_load_state("networkidle", timeout=5000)
            return f"✅ Clicked element: {selector}\nCurrent URL: {self.page.url}"
        except Exception as e:
            return f"❌ Click failed on {selector}: {e}"
    
    @xray
    def extract_links(self, filter_pattern: str = "") -> str:
        """Extract all links from the current page.
        
        Args:
            filter_pattern: Optional pattern to filter links
        """
        if not self.page:
            return "❌ No page loaded"
        
        try:
            links = self.page.eval_on_selector_all(
                'a[href]',
                'elements => elements.map(e => ({text: e.innerText, href: e.href}))'
            )
            
            if filter_pattern:
                links = [link for link in links if filter_pattern in link['href']]
            
            if not links:
                return "No links found" + (f" matching '{filter_pattern}'" if filter_pattern else "")
            
            result = f"🔗 Found {len(links)} links:\n"
            for link in links[:10]:  # Show first 10
                result += f"  - {link['text'][:30]}: {link['href']}\n"
            
            if len(links) > 10:
                result += f"  ... and {len(links) - 10} more"
            
            return result
        except Exception as e:
            return f"❌ Link extraction failed: {e}"
    
    @xray
    def wait_for_element(self, selector: str, timeout: int = 5000) -> str:
        """Wait for an element to appear on the page.
        
        Args:
            selector: CSS selector to wait for
            timeout: Maximum wait time in milliseconds
        """
        if not self.page:
            return "❌ No page loaded"
        
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return f"✅ Element {selector} appeared"
        except Exception as e:
            return f"❌ Element {selector} did not appear within {timeout}ms"
    
    @xray
    def execute_javascript(self, script: str) -> str:
        """Execute JavaScript code on the page.
        
        Args:
            script: JavaScript code to execute
        """
        if not self.page:
            return "❌ No page loaded"
        
        try:
            result = self.page.evaluate(script)
            return f"✅ JavaScript executed. Result: {result}"
        except Exception as e:
            return f"❌ JavaScript execution failed: {e}"
    
    @xray
    def get_page_info(self) -> str:
        """Get information about the current page."""
        if not self.page:
            return "❌ No page loaded"
        
        info = {
            "url": self.page.url,
            "title": self.page.title(),
            "viewport": self.page.viewport_size,
        }
        
        return f"📊 Page info:\n" + json.dumps(info, indent=2)
    
    @xray
    def get_session_info(self) -> str:
        """Get information about the browser session."""
        info = {
            "browser_running": self.browser is not None,
            "current_url": self.page.url if self.page else None,
            "visited_urls": self.visited_urls,
            "screenshots_taken": len(self.screenshots),
            "screenshot_files": self.screenshots,
        }
        
        return f"📊 Session info:\n" + json.dumps(info, indent=2)
    
    @xray
    def close_browser(self) -> str:
        """Close the browser and clean up resources."""
        if self.page:
            self.page.close()
            self.page = None
        if self.browser:
            self.browser.close()
            self.browser = None
        if self.playwright:
            self.playwright.stop()
            self.playwright = None
        
        return "✅ Browser closed and resources cleaned up"


# Create browser automation instance
browser = BrowserAutomation()

# Create the Playwright automation agent with stateful tools
agent = Agent(
    name="playwright_agent",
    system_prompt="prompt.md",
    tools=browser,  # Pass the entire class instance - all methods become tools
    max_iterations=20  # More iterations for complex web automation
)


def main():
    """Run the Playwright agent in interactive mode."""
    print("🌐 Playwright Web Automation Agent")
    print("Stateful browser automation with persistent session")
    print("Type 'quit' to exit\n")

    # Interactive conversation loop
    while True:
        user_input = input("You: ").strip()

        if user_input.lower() in ['quit', 'exit', 'q']:
            # Clean up browser resources before exit
            try:
                browser.close_browser()
            except:
                pass
            print("👋 Goodbye!")
            break

        if not user_input:
            continue

        # Get response from agent
        response = agent.input(user_input)
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    if not PLAYWRIGHT_AVAILABLE:
        print("⚠️  Playwright is not installed!")
        print("To use this agent, run:")
        print("  pip install -r requirements.txt")
        print("  playwright install chromium\n")
    else:
        print("🌐 Playwright Web Automation Agent initialized!")
        print("Stateful browser automation with persistent session\n")

        print("Available browser tools:")
        for tool_name in agent.list_tools():
            print(f"  🔧 {tool_name}")

        print("\n📚 Example commands:")
        print('  "Start the browser and go to example.com"')
        print('  "Take a screenshot of the page"')
        print('  "Extract all links from the page"')
        print('  "Get the page title and URL"')

        print("\n💡 Tips:")
        print("  - Browser state persists across commands")
        print("  - Always start_browser() before other operations")
        print("  - Use close_browser() when done (or type 'quit')")
        print("  - Ask for session_info() to see browser state\n")

        print("=" * 50 + "\n")

        # Start interactive mode
        main()