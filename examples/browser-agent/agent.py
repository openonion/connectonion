"""Browser Agent - Web automation with navigation and screenshot capabilities"""

import os
from connectonion import Agent, xray
from connectonion.useful_plugins import reflection, react
from dotenv import load_dotenv
from pathlib import Path
import time

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit("Install Playwright: pip install playwright && playwright install")

# Load environment variables from .env file
load_dotenv()

# Validate API key
if not os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY') == 'sk-your-key-here':
    print("⚠️  Warning: OPENAI_API_KEY not set or using placeholder!")
    print("Please set your OpenAI API key in the .env file or as an environment variable.")
    print("Example: export OPENAI_API_KEY='your-actual-api-key'")
    import sys
    sys.exit(1)


class BrowserAutomation:
    """Simple browser automation with Chromium."""
    
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None
        self._screenshots = []
    
    @xray
    def start_browser(self, headless: bool = True, width: int = 1280, height: int = 720) -> str:
        """Start a Chromium browser session with custom viewport size."""
        if self._browser:
            return "Browser already running. Use close_browser() first to restart."
        
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=headless)
        self._page = self._browser.new_page()
        self._page.set_viewport_size({"width": width, "height": height})
        
        return f"Chromium browser started (headless={headless}, viewport: {width}x{height})"
    
    @xray
    def set_viewport_size(self, width: int = 1280, height: int = 720) -> str:
        """Change the browser viewport size (affects how pages render and screenshot size)."""
        self._page.set_viewport_size({"width": width, "height": height})
        return f"Viewport size set to {width}x{height}"
    
    @xray
    def navigate(self, url: str) -> str:
        """Navigate to a URL."""
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        self._page.goto(url, wait_until="load", timeout=30000)
        title = self._page.title()
        
        return f"Navigated to: {url}\nPage title: {title}"
    
    @xray
    def take_screenshot(
        self, 
        path: str = "", 
        full_page: bool = False,
        width: int = 1280, 
        height: int = 720
    ) -> str:
        """Take a screenshot and save it to specified path.
        
        Args:
            path: File path (supports directories) or filename. Auto-generates if empty.
            full_page: If True, captures entire page height. If False, captures viewport only.
            width: Viewport width in pixels (affects screenshot size).
            height: Viewport height in pixels (affects screenshot size).
        """
        # Set viewport size if different from current
        current_viewport = self._page.viewport_size
        if current_viewport["width"] != width or current_viewport["height"] != height:
            self._page.set_viewport_size({"width": width, "height": height})
        
        # Handle path/filename
        if not path:
            timestamp = int(time.time())
            final_path = f"screenshot_{timestamp}.png"
        else:
            # Check if path is a directory
            path_obj = Path(path)
            
            if path.endswith('/') or path.endswith('\\') or (path_obj.exists() and path_obj.is_dir()):
                # It's a directory, generate filename
                timestamp = int(time.time())
                final_path = str(path_obj / f"screenshot_{timestamp}.png")
            else:
                # It's a filename/path
                final_path = path
                if not final_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                    final_path += ".png"
            
            # Ensure directory exists
            Path(final_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Take screenshot
        self._page.screenshot(path=final_path, full_page=full_page)
        self._screenshots.append(final_path)
        
        size_info = f"viewport ({width}x{height})" if not full_page else f"full page (width: {width}px)"
        return f"Screenshot saved: {final_path} ({size_info})"
    
    @xray
    def scrape_content(self, selector: str = "body") -> str:
        """Extract text content from the page."""
        if selector == "body":
            content = self._page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script, style, noscript');
                    scripts.forEach(s => s.remove());
                    return document.body.innerText.trim();
                }
            """)
        else:
            element = self._page.locator(selector).first
            content = element.text_content() if element.count() > 0 else "Element not found"
        
        if len(content) > 2000:
            content = content[:2000] + "\n[Content truncated...]"
        
        return f"Content from '{selector}':\n{content}"
    
    @xray
    def extract_links(self) -> str:
        """Extract all links from the current page."""
        links = self._page.evaluate("""
            () => {
                const linkElements = Array.from(document.querySelectorAll('a[href]'));
                return linkElements.slice(0, 20).map(link => ({
                    text: link.textContent.trim() || '[No text]',
                    url: link.href
                }));
            }
        """)
        
        if not links:
            return "No links found on the page"
        
        result = f"Found {len(links)} links:\n"
        for i, link in enumerate(links, 1):
            result += f"{i}. {link['text']} -> {link['url']}\n"
        
        return result.rstrip()
    
    @xray
    def close_browser(self) -> str:
        """Close the browser and clean up resources."""
        if self._page:
            self._page.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        
        self._page = None
        self._browser = None
        self._playwright = None
        
        screenshots_info = f"Screenshots saved: {', '.join(self._screenshots)}" if self._screenshots else "No screenshots taken"
        self._screenshots.clear()
        
        return f"Browser closed successfully. {screenshots_info}"


# Create browser automation instance
browser = BrowserAutomation()

# Create the browser agent - pass the class instance directly!
agent = Agent(
    name="browser_agent",
    system_prompt="prompts/browser_agent.md",
    tools=[browser],  # ConnectOnion automatically extracts all public methods
    model="gpt-4o-mini",
    max_iterations=15,
    plugins=[reflection, react]  # Add reflection and ReAct reasoning
)


if __name__ == "__main__":
    print("🌐 ConnectOnion Browser Agent initialized!")
    print("Your AI assistant for web automation with reflection & reasoning\n")
    print("Available capabilities:")
    print("🚀 Browser control - Start/stop Chromium browser with custom viewport")
    print("🧭 Navigation - Visit websites")
    print("📸 Advanced screenshots - Custom paths, sizes, full-page capture")
    print("🔍 Content extraction - Scrape text and links")
    print("📏 Viewport control - Adjust browser window size")
    print("💭 Reflection - Learn from each action")
    print("🤔 ReAct - Reason about actions and plan next steps")
    print("\nTry: 'Open Google and take a screenshot'")
    print("     'Take a full-page screenshot and save to ./screenshots/'")
    print("     'Set viewport to 1920x1080 and navigate to example.com'")
    
    # Interactive loop
    print("\nType 'exit' or 'quit' to end the conversation.")
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Closing browser and exiting...")
            browser.close_browser()
            break
        if not user_input:
            continue
        assistant_reply = agent.input(user_input)
        print(f"\nAssistant: {assistant_reply}")
    print("Goodbye!")