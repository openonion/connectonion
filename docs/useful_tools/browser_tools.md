# Browser Tools

Natural language browser automation via [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) — a stealth-patched, API-compatible Playwright fork that hides driver-level automation tells out of the box. On top of that, every mouse, keyboard and scroll action is **humanized** so the *behavior* looks human too, not just the browser (see [Anti-Detection](#anti-detection)). Navigate, click, type, screenshot — no CSS selectors needed.

## Installation

```bash
pip install patchright
patchright install chrome
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

## Portable Login State

The persistent profile above lives at `~/.co/browser_profile/` and cannot be moved safely across operating systems because its cookies are encrypted per machine. To reuse a login on another machine or inside a Linux deploy container, export a Playwright storage state JSON and inject it when constructing the browser:

```python
# On your machine, headed: log in by hand, then export
browser = BrowserAutomation(headless=False)
browser.go_to("https://www.linkedin.com/login")
input("Log in, then press Enter...")
browser.save_state("linkedin_state.json")

# On the deployed agent: inject before the first navigation
browser = BrowserAutomation(seed_state="linkedin_state.json")
```

`seed_state` injects cookies with `add_cookies()` after the persistent context opens. Unset `seed_state` keeps the current behavior.

> **Treat the state file as a secret.** It holds live session cookies — anyone with it can act as the logged-in user. Add it to `.gitignore`, never commit it or bake it into a Docker image, and inject it on deploy through the secret store rather than shipping it in the project tarball.

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

When you have a stable CSS selector, click it directly:

```python
browser.click_element_by_selector('button[type="submit"]')
browser.click_element_by_selector('button', text="Sign in")
browser.click_element_by_selector('.item', index=2)
```

To click inside an iframe, including a cross-origin one (an embedded widget, payment form, or editor) that main-page selectors cannot reach, pass `frame_url_contains` or `frame_name`:

```python
browser.click_element_by_selector(
    '#subscribe',
    frame_url_contains="checkout",
)
```

The click is dispatched through Playwright's input layer as a real pointer event at the element's coordinates. Text matching remains main-frame only.

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

Typing is humanized: Latin text is entered key-by-key with a human, right-skewed rhythm, and CJK (Chinese/Japanese/Korean) is entered the way people actually do — a real paste, falling back to IME composition when a field blocks paste — never a bare programmatic insert. See [Anti-Detection](#anti-detection).

### Scrolling

```python
browser.scroll()                                     # 5 scrolls on main content
browser.scroll(times=3, description="the sidebar")  # Scroll a specific area
```

Scrolls with real mouse-wheel events first (human-like, no LLM), falling back to an AI-picked JS strategy (element scroll, page scroll) only if the wheel doesn't move the page.

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

One `BrowserAutomation` instance is safe to reuse across turns and concurrent hosted sessions. Public methods are serialized onto one internal browser worker thread, so Playwright's sync API is always called from the thread that owns it. When `bind_browser_session` is enabled, each hosted session gets its own tab in the shared browser context.

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

## Proxy

Set `BROWSER_PROXY` to route browser traffic through an HTTP or SOCKS proxy — for example to control the egress IP, test geo-specific behavior, or comply with a corporate network policy:

```bash
BROWSER_PROXY=http://user:pass@host:port
BROWSER_PROXY=socks5://host:port
```

`BROWSER_PROXY` is read when `open_browser()` launches the context. Leave it unset for direct egress. Use a proxy only against sites whose terms permit it.

## Anti-Detection

Bot detection works on two layers, and the browser tools address both — automatically, with no configuration and no change to any method you call.

**Driver layer (Patchright).** The stealth-patched Playwright fork removes the automation tells a page can read directly — `navigator.webdriver`, the `Runtime.enable` / CDP leaks, the "controlled by automated test software" infobar. It also launches real Google Chrome (not "Chrome for Testing") when available, uses the real window size instead of a fixed viewport, and enables software WebGL so a GPU-less server still reports a WebGL context. Check it with `co browser status` or `co doctor`.

**Behavior layer (humanized input).** Even with a clean browser, *how* it moves gives automation away — instant cursor teleports, zero-dwell clicks, uniform keystroke timing, programmatic scroll jumps. Every action here is shaped to look human instead:

- **Mouse** — curved (Bézier) paths with a real acceleration/deceleration velocity profile and a small landing overshoot; clicks land on a gaussian spread near the target (not dead-center) with a randomized press dwell.
- **Keyboard** — character-by-character with right-skewed (log-normal) timing and the occasional pause, per a per-session "persona" so the cadence isn't a fixed fingerprint across runs. CJK text is entered by a trusted paste (IME composition fallback).
- **Scroll** — real mouse-wheel events sized like a physical wheel or trackpad, with overshoot-and-correct — not a `scrollBy()` jump.

This holds up against behavioral checkers (e.g. sannysoft, BrowserScan, CreepJS, rebrowser-bot-detector, reCAPTCHA v3). One thing it can't change is **IP reputation** — a datacenter IP still reads as suspicious to IP-aware detectors regardless of behavior; route through a residential [proxy](#proxy) for those.

## Notes

- Uses Google Chrome if installed (better site compatibility); if no browser exists, chromium is auto-installed per-user (no admin rights, v1.2.1+)
- Viewport defaults to 1920×1200 for maximum content visibility
- Output is truncated when used as an agent tool to prevent token overflow
- Runs natively on Windows since v1.2.1 (named-pipe transport — no WSL), plus macOS and Linux
