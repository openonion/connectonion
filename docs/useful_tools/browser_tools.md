# Browser Tools

Natural language browser automation via Playwright. Navigate, click, type, screenshot — no CSS selectors needed.

## Installation

```bash
pip install playwright
playwright install chromium
```

## Usage

```python
from connectonion import Agent
from connectonion.useful_tools.browser_tools import BrowserAutomation

browser = BrowserAutomation()
agent = Agent("web", tools=[browser])

agent.input("go to github.com and take a screenshot")
```

## Quick Start (no agent)

```python
from connectonion.useful_tools.browser_tools import BrowserAutomation

with BrowserAutomation() as browser:
    browser.go_to("https://example.com")
    browser.click("the contact button")
    browser.keyboard_type("hello@example.com")
    browser.take_screenshot()
    browser.close()
```

## Persistent Profile

Browser state (cookies, sessions, localStorage) is saved automatically to `~/.co/browser_profile/`. On subsequent runs the browser is already logged into any site you've previously authenticated.

```python
# First run — log in manually
browser = BrowserAutomation()
browser.go_to("https://x.com")
browser.wait_for_manual_login("X.com")   # You log in, 2FA, etc.
# Session saved to ~/.co/browser_profile/

# Next run — already logged in
browser = BrowserAutomation()
browser.go_to("https://x.com")           # Session restored automatically
```

## API

### Navigation

```python
browser.go_to("https://example.com")
browser.go_to("example.com")             # https:// added automatically
browser.get_current_url()                # → "https://example.com"
```

### Screenshots

```python
browser.take_screenshot()                # Returns base64 image (auto-saved to .tmp/)
browser.take_screenshot("my_step.png")  # Custom filename
browser.take_screenshot(full_page=True) # Capture full page height
```

Screenshots are saved to `.tmp/` in your working directory.

### Clicking

```python
browser.click("the submit button")
browser.click("Sign In link")
browser.click("email input field")       # Uses AI to find by description
```

Element finding uses a vision LLM — describe what you see, not a CSS selector.

### Typing

```python
browser.click("the email input")
browser.keyboard_type("user@example.com")

browser.keyboard_press("Enter")
browser.keyboard_press("Control+Enter")
browser.keyboard_press("Escape")
browser.keyboard_press("Tab")
```

After `keyboard_type()`, call `take_screenshot()` to verify the text landed in the right field.

### Scrolling

```python
browser.scroll()                                     # 5 scrolls on main content
browser.scroll(times=3, description="the sidebar")  # Scroll a specific area
```

Uses AI to pick the best scroll strategy (element scroll, page scroll, or mouse wheel).

### Reading Page Content

```python
browser.get_text()                           # All visible text from the page
browser.get_links_from_page()                # All unique URLs
browser.get_links_from_page("github.com")   # URLs containing "github.com"
```

### Forms

```python
browser.select_option("country dropdown", "Australia")
browser.check_checkbox("I agree to terms")
browser.check_checkbox("newsletter", checked=False)  # Uncheck
```

### Waiting

```python
browser.wait(2)                              # Wait 2 seconds
browser.wait_for_element("the save button") # Wait for element to appear
browser.wait_for_text("Payment successful") # Wait for text on page
browser.wait_for_manual_login("Gmail")      # Pause for 2FA/CAPTCHA
```

### Viewport

```python
browser.set_viewport(1920, 1080)
browser.set_viewport(375, 812)   # iPhone
```

## Headless vs Visible

```python
BrowserAutomation(headless=True)   # Default — runs in background (faster)
BrowserAutomation(headless=False)  # Opens visible browser window
```

## Use with Agent

```python
from connectonion import Agent
from connectonion.useful_tools.browser_tools import BrowserAutomation

browser = BrowserAutomation(headless=False)  # Visible for debugging
agent = Agent("scraper", tools=[browser], model="co/gemini-2.5-pro")

agent.input("Go to news.ycombinator.com, get the top 5 story titles")
agent.input("Navigate to github.com/trending and screenshot the page")
agent.input("Fill in the contact form on example.com with test data")
```

## Common Patterns

### Login once, reuse session

```python
browser = BrowserAutomation()
browser.go_to("https://app.example.com/login")
browser.wait_for_manual_login("example.com")  # Log in once

# Every run after: session is restored from ~/.co/browser_profile/
```

### Screenshot workflow

```python
browser.go_to("https://example.com")
browser.click("Login")
browser.keyboard_type("user@example.com")
browser.keyboard_press("Tab")
browser.keyboard_type("password123")
browser.take_screenshot("before_submit.png")
browser.keyboard_press("Enter")
browser.wait(2)
browser.take_screenshot("after_login.png")
```

### Data extraction

```python
browser.go_to("https://example.com/products")
text = browser.get_text()
links = browser.get_links_from_page("/product/")
```

## Notes

- Uses Google Chrome if installed (better site compatibility), otherwise falls back to Chromium
- Viewport defaults to 1920×1200 for maximum content visibility
- Output is truncated when used as an agent tool to prevent token overflow
- Windows is not supported
