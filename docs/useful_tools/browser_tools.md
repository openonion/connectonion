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

## Portable Login State (cross-machine)

The persistent profile above lives at `~/.co/browser_profile/` and **can't be moved**: its cookies are encrypted per-OS, so copying the folder to another machine (or into a Linux deploy container) won't carry the login.

To reuse a login across machines, export the session as a plaintext, portable `storage_state` JSON and inject it on the other side:

```python
# On your machine (headed): log in by hand, then export
browser = BrowserAutomation(headless=False)
browser.go_to("https://www.linkedin.com/login")
input("Log in, then press Enter...")
browser.save_state("linkedin_state.json")   # cookies + origins, plaintext, portable

# On the deployed agent: inject at startup, before any navigation
browser = BrowserAutomation(seed_state="linkedin_state.json")
# the first open_browser() applies the cookies once → starts already signed in
```

Ship `linkedin_state.json` with the deploy (it's a small JSON, not the profile dir). `seed_state` injects via `add_cookies` because `launch_persistent_context()` can't accept a `storage_state` path. Unset `seed_state` → no injection, behaviour unchanged.

> The cookies authenticate, but a different egress IP (e.g. a datacenter IP on a cloud deploy) can still trigger re-verification. Pair with `BROWSER_PROXY` (below) when the target is IP-sensitive.

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

When you have a stable CSS selector, click it directly (faster, deterministic):

```python
browser.click_element_by_selector('button[type="submit"]')
browser.click_element_by_selector('button', text="Sign in")   # disambiguate by visible text
browser.click_element_by_selector('.item', index=2)           # nth match (0-based)
```

To click inside an iframe — including a **cross-origin** one like a reCAPTCHA
"I'm not a robot" checkbox that main-page selectors can't reach — pass
`frame_url_contains` or `frame_name`:

```python
browser.click_element_by_selector('.recaptcha-checkbox-border', frame_url_contains="recaptcha")
```

The click goes through Playwright's input layer, so the event is trusted
(`isTrusted`) — a JS `el.click()` is not, and bot checks reject it. (`text`
matching stays main-frame only.)

### Hover and Advanced Mouse

```python
browser.hover("the Like button")         # Hover to reveal menus/tooltips
browser.take_screenshot()                # See what appeared
browser.mouse_click(x, y)               # Click exact coordinates (for hover menus)

browser.right_click("the file icon")    # Open context menu
browser.double_click("the file name")   # Double-click to open/select
```

`mouse_click(x, y)` is useful after `hover()` — clicking by description would re-scan the DOM and dismiss the hover menu.

### System Info

```python
info = browser.get_system_info()
# → "OS: macOS. Use Meta for shortcuts (Meta+a select all, Meta+c copy...)"
# → "OS: Windows. Use Control for shortcuts..."
```

Call this before using keyboard shortcuts to get the correct modifier key for the current OS.

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

### File Uploads

```python
# Upload to an existing file input. Hidden inputs are supported.
browser.upload_file_by_selector('input[type="file"]', "cover.png")

# Click an upload button that opens the OS file picker, then attach the file.
browser.upload_file_after_click_by_selector(
    "button",
    "cover.png",
    text="Upload from computer",
)
```

Both upload helpers accept `frame_url_contains` and `frame_name` for editors that render upload controls inside iframes. Pass `index` when the selector matches multiple file inputs or upload buttons.

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
BrowserAutomation(headless=False)  # Default — opens visible browser window
BrowserAutomation(headless=True)   # Runs in background (faster, no window)
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

One `BrowserAutomation` instance is **safe to reuse across turns and across
concurrent hosted sessions** — keep a single shared browser, don't create or
close+reopen one per turn. Playwright's sync API binds to the thread that
started it, and `host()` runs each turn on an arbitrary pool thread; every
public method is serialized onto one dedicated internal worker thread, so calls
from any thread land on the right one and the browser (and its login state)
persists across turns.

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

## Proxy (BROWSER_PROXY)

Set the `BROWSER_PROXY` env var to route the browser's traffic through a proxy — e.g. so a cloud-deployed agent exits from a residential IP instead of the datacenter IP it runs on (which anti-bot systems distrust):

```bash
BROWSER_PROXY=http://user:pass@host:port   # HTTP proxy with auth (e.g. a residential proxy service)
BROWSER_PROXY=socks5://host:port           # SOCKS5 relay (no auth — Chromium ignores SOCKS auth)
```

Read at `open_browser()`; unset → no proxy (behaviour unchanged). On a deploy, put it in `.env` so it's injected as a secret, never baked into the image.

## Notes

- Uses Google Chrome if installed (better site compatibility), otherwise falls back to Chromium
- Viewport defaults to 1920×1200 for maximum content visibility
- Output is truncated when used as an agent tool to prevent token overflow
- Windows is not supported
