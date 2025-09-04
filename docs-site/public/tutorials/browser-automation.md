# Browser Automation with ConnectOnion

Learn how to build a web automation agent using ConnectOnion and Playwright. This tutorial shows you how to create an AI-powered browser that can navigate websites, take screenshots, and extract information.

## What You'll Build

A browser automation agent that can:
- Navigate to any website
- Take screenshots (normal or full-page)
- Extract text content and links
- Maintain browser state across multiple commands
- Respond to natural language instructions

## Prerequisites

```bash
pip install connectonion playwright python-dotenv
playwright install  # Download browser drivers
```

## The Complete Code

Let's start with the full working example, then break it down:

```python
"""Browser Agent - Web automation with ConnectOnion"""

import os
from connectonion import Agent, xray
from dotenv import load_dotenv
from pathlib import Path
import time

from playwright.sync_api import sync_playwright

# Load environment variables
load_dotenv()

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
    def navigate(self, url: str) -> str:
        """Navigate to a URL."""
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        
        self._page.goto(url, wait_until="load", timeout=30000)
        title = self._page.title()
        
        return f"Navigated to: {url}\nPage title: {title}"
    
    @xray
    def take_screenshot(self, path: str = "", full_page: bool = False) -> str:
        """Take a screenshot and save it to specified path."""
        if not path:
            timestamp = int(time.time())
            path = f"screenshot_{timestamp}.png"
        
        self._page.screenshot(path=path, full_page=full_page)
        self._screenshots.append(path)
        
        return f"Screenshot saved: {path}"
    
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

# Create browser instance
browser = BrowserAutomation()

# Create the agent - pass the class instance directly!
agent = Agent(
    name="browser_agent",
    system_prompt="You are a web automation assistant. Start the browser, navigate, and help users interact with websites.",
    tools=[browser],  # ConnectOnion auto-discovers all methods
    model="gpt-4o-mini"
)

if __name__ == "__main__":
    print("🌐 Browser Agent Ready!")
    print("\nExample commands:")
    print("  - Navigate to example.com and take a screenshot")
    print("  - Extract all links from the page")
    print("  - Take a full-page screenshot")
    
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            browser.close_browser()
            break
        if not user_input:
            continue
        
        response = agent.input(user_input)
        print(f"\nAssistant: {response}")
```

## How It Works

### 1. Class-Based Tools with Shared State

The key pattern here is using a **class instance as a tool**. This lets multiple methods share state (the browser session):

```python
class BrowserAutomation:
    def __init__(self):
        self._playwright = None
        self._browser = None
        self._page = None  # Shared browser page
        self._screenshots = []  # Track screenshots
```

### 2. Pass the Instance, Not Methods

ConnectOnion's magic happens when you pass the class instance:

```python
browser = BrowserAutomation()

agent = Agent(
    name="browser_agent",
    tools=[browser],  # ✅ Pass the instance!
)
```

ConnectOnion automatically:
- Discovers all public methods
- Converts them to tools with proper schemas
- Preserves shared state between calls

**Don't do this:**
```python
# ❌ DON'T list methods individually
tools=[browser.start_browser, browser.navigate, browser.take_screenshot]
```

### 3. The @xray Decorator

Add `@xray` to any method to debug what the agent is doing:

```python
@xray
def navigate(self, url: str) -> str:
    """Navigate to a URL."""
    # Inside here, you can access:
    # xray.agent - The agent calling this
    # xray.task - What the user asked for
    # xray.iteration - Which tool call iteration this is
    
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    
    self._page.goto(url, wait_until="load", timeout=30000)
    title = self._page.title()
    
    return f"Navigated to: {url}\nPage title: {title}"
```

### 4. Natural Error Handling

Notice there are no try-except blocks. If something goes wrong (like browser not started), Python will throw a clear error. This keeps the code simple and honest.

## Step-by-Step Usage

### Step 1: Basic Navigation

```python
# User: "Navigate to docs.connectonion.com"

# What happens:
# 1. Agent calls start_browser() - launches Chromium
# 2. Agent calls navigate("https://docs.connectonion.com")
# 3. Returns: "Navigated to: https://docs.connectonion.com
#            Page title: ConnectOnion Documentation"
```

### Step 2: Taking Screenshots

```python
# User: "Take a screenshot and save it as docs.png"

# Agent calls:
browser.take_screenshot(path="docs.png")

# Returns: "Screenshot saved: docs.png"
```

### Step 3: Extracting Content

```python
# User: "What links are on this page?"

# Agent calls:
browser.extract_links()

# Returns: "Found 20 links:
#          1. Introduction -> https://docs.connectonion.com/intro
#          2. Quick Start -> https://docs.connectonion.com/quickstart
#          ..."
```

### Step 4: Full-Page Screenshots

```python
# User: "Take a full-page screenshot"

# Agent calls:
browser.take_screenshot(full_page=True)

# Returns: "Screenshot saved: screenshot_1234567890.png"
```

## Advanced Features

### Custom Viewport Sizes

```python
def set_viewport_size(self, width: int = 1280, height: int = 720) -> str:
    """Change the browser viewport size."""
    self._page.set_viewport_size({"width": width, "height": height})
    return f"Viewport size set to {width}x{height}"
```

### Scraping Specific Elements

```python
# Scrape a specific CSS selector
def scrape_content(self, selector: str = "body") -> str:
    """Extract text from specific elements."""
    element = self._page.locator(selector).first
    content = element.text_content() if element.count() > 0 else "Element not found"
    return content
```

### Headless vs Visible Browser

```python
# Run with visible browser for debugging
browser.start_browser(headless=False)

# Run headless for automation (default)
browser.start_browser(headless=True)
```

## Running the Example

1. **Save the code** as `browser_agent.py`

2. **Create `.env` file**:
```bash
OPENAI_API_KEY=your-api-key-here
```

3. **Run it**:
```bash
python browser_agent.py
```

4. **Try these commands**:
```
You: Start browser and go to example.com
Assistant: I've started the browser and navigated to example.com. 
           Page title: Example Domain

You: Take a screenshot
Assistant: Screenshot saved: screenshot_1234567890.png

You: What's on the page?
Assistant: The page contains a simple example domain message explaining 
           that this domain is for use in illustrative examples...

You: Close the browser
Assistant: Browser closed successfully. Screenshots saved: screenshot_1234567890.png
```

## Key Concepts

### 1. Stateful Tools
The browser maintains state across multiple tool calls. Once you navigate to a page, subsequent commands operate on that same page.

### 2. Natural Language Control
Users don't need to know the method names. They can say "go to Google" instead of "navigate('https://google.com')".

### 3. Automatic Tool Discovery
ConnectOnion finds all public methods automatically. Add a new method to the class, and it becomes a tool instantly.

### 4. Clean, Simple Code
No over-engineering. No excessive error handling. Just straightforward code that does what it needs to do.

## Common Patterns

### Pattern 1: Multi-Step Workflows

```python
# User gives complex instruction
"Go to GitHub, search for ConnectOnion, and take a screenshot of the results"

# Agent breaks it down:
1. browser.start_browser()
2. browser.navigate("https://github.com")
3. browser.navigate("https://github.com/search?q=connectonion")
4. browser.take_screenshot()
```

### Pattern 2: Information Extraction

```python
# User wants specific data
"Find all documentation links on the ConnectOnion docs site"

# Agent:
1. browser.navigate("https://docs.connectonion.com")
2. browser.extract_links()
3. Filters and presents only documentation links
```

### Pattern 3: Visual Documentation

```python
# User needs visual proof
"Take screenshots of the login flow on example.com"

# Agent:
1. browser.navigate("https://example.com/login")
2. browser.take_screenshot(path="login_page.png")
3. browser.navigate("https://example.com/dashboard")
4. browser.take_screenshot(path="dashboard.png")
```

## Tips & Best Practices

### 1. Keep Methods Simple
Each method should do one thing well. Don't combine navigation and screenshots into one method.

### 2. Return Useful Information
Always return what happened:
```python
return f"Navigated to: {url}\nPage title: {title}"
# Not just: return "OK"
```

### 3. Use Type Hints
Type hints help ConnectOnion generate proper schemas:
```python
def take_screenshot(self, path: str = "", full_page: bool = False) -> str:
    # ConnectOnion knows: path is string, full_page is boolean
```

### 4. Descriptive Docstrings
The first line becomes the tool description for the LLM:
```python
def extract_links(self) -> str:
    """Extract all links from the current page."""  # LLM sees this
```

## Extending the Browser Agent

Want to add more features? Just add methods to the class:

```python
class BrowserAutomation:
    # ... existing methods ...
    
    def click(self, selector: str) -> str:
        """Click on an element."""
        self._page.click(selector)
        return f"Clicked on {selector}"
    
    def fill_form(self, selector: str, text: str) -> str:
        """Fill a form field with text."""
        self._page.fill(selector, text)
        return f"Filled {selector} with text"
    
    def wait_for_element(self, selector: str, timeout: int = 5000) -> str:
        """Wait for an element to appear."""
        self._page.wait_for_selector(selector, timeout=timeout)
        return f"Element {selector} is now visible"
```

These automatically become available as tools!

## Troubleshooting

### Browser doesn't start
- Make sure Playwright is installed: `playwright install`
- Check if you have necessary system dependencies

### Screenshots not saving
- Check file permissions in the directory
- Ensure the path is valid

### Page navigation fails
- Some sites block automation - try with `headless=False`
- Increase timeout if sites are slow: `timeout=60000`

## Summary

You've learned how to:
- Build a browser automation agent with ConnectOnion
- Use class instances as stateful tools
- Control browsers with natural language
- Keep code simple without over-engineering

The key insight: **Pass class instances to ConnectOnion, not individual methods.** This gives you stateful tools that can work together seamlessly.

## Next Steps

- Add more browser automation methods
- Create specialized agents for testing, scraping, or monitoring
- Combine with other tools for complex workflows
- Check out the [ConnectOnion documentation](https://docs.connectonion.com) for more patterns

Remember: Keep simple things simple, make complicated things possible!