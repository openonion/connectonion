# Browser Tools

Natural language browser automation via [Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) — a stealth-patched, API-compatible Playwright fork that hides driver-level automation tells out of the box. Navigate, click, type, screenshot — no CSS selectors needed.

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

### Synchronous API, async runtime

`BrowserAutomation` remains synchronous in 1.8: existing calls, context managers,
method names, signatures, and return values do not require an `await`. Internally,
the class owns one async browser core on a private event-loop thread. This removes
the old synchronous Patchright implementation from the execution path while
preserving existing Python and Agent integrations.

Calling these synchronous methods from a thread that already runs an asyncio loop
is supported; the call blocks that caller until its browser operation completes.
Calling from the browser's own private runtime thread raises a clear `RuntimeError`
instead of deadlocking. An unbound `close()` closes the shared browser and joins the
runtime thread; a session-bound `close()` releases only that session's tab.

Compatibility policy for 1.8: no public `BrowserAutomation` method is deprecated,
and the async core remains internal. `LegacyBrowserAutomation` is an internal test
oracle for comparing the 1.7 contract; it is not a supported import and may be
removed after the 1.8 transition without a deprecation period.

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
The 1.8 async core keeps that same selection contract: it awaits DOM extraction,
then runs the synchronous model match outside the browser event loop. A slow
provider may delay the requesting tab, but it does not stop unrelated tabs from
reading or acting. Main-page, named-iframe, and open-shadow-root targets retain
their extracted locators or coordinate fallbacks.

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

Stable workflows can avoid a page rescan with
`click_element_by_selector(selector, index=0, text="")` and
`type_text_by_selector(selector, text, index=0)`. Selector clicks use humanized
pointer input when an element exposes a bounding box and retain a forced locator
fallback for elements without one. Use `frame_url_contains` or `frame_name` when
the target lives in an iframe; the index applies across all matching frames.

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

Before replacing text, inspect focus instead of typing a canary or discovering a
missed click after state has been destroyed:

```python
focus = browser.get_focused_element()
# JSON includes tag, role, aria_label, contenteditable, and is_editable.
# Password values are never returned.
browser.keyboard_press("Meta+a")
browser.keyboard_press("Backspace")
```

`keyboard_press()` refuses select-all, Backspace, and Delete when the focused
element is not editable. For an intentional page-level shortcut, pass
`allow_non_editable=True`. After `keyboard_type()`, call `take_screenshot()` to
verify the text landed in the expected field.

Inspection covers the top-level document and open shadow roots. Focus inside an
iframe is reported as the iframe and fails the editable check; closed shadow
roots are likewise opaque. Target the field directly in those cases, and only
use the override after independently verifying the destination.

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

### Local Page and Frame Scripts

Keep site-specific extraction or verification logic in a reviewed local
JavaScript file, then execute it in the current authenticated page:

```python
# verify.js: (args) => ({ ok: document.title === args.title })
browser.run_page_script("verify.js", '{"title": "Dashboard"}')

browser.run_frame_script(
    "verify.js",
    '{"title": "Composer"}',
    frame_name="editor",
)
```

`run_frame_script()` scans matching frames and, by default, stops at the first
object that returns `{"ok": true}`. Set `first_ok=False` to retain results from
every matching frame. Relative script paths resolve from the current working
directory; arguments must be valid JSON.

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
agent = Agent("scraper", tools=[browser], model="co/gemini-3.7-flash")

agent.input("Go to news.ycombinator.com, get the top 5 story titles")
agent.input("Navigate to github.com/trending and screenshot the page")
agent.input("Fill in the contact form on example.com with test data")
```

One `BrowserAutomation` instance is safe to reuse across turns and concurrent hosted sessions. Public methods are serialized onto one internal browser worker thread, so Playwright's sync API is always called from the thread that owns it. When `bind_browser_session` is enabled, each hosted session gets its own tab in the shared browser context.

That worker-thread behavior remains the public Python contract until #500 adds
the compatibility facade. The replacement core is still internal; do not import
it as an application API. The `co browser` daemon now owns that async core
directly: independent tabs interleave, same-tab operations serialize, and the
POSIX/Windows transports bound connections, reads, writes, and shutdown. The
lifecycle, concurrency, cancellation, and compatibility boundaries are recorded
in [DD-054](../design-decisions/054-one-async-browser-runtime.md).
`BrowserAutomation` remains the supported Python API.

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

## Notes

- Uses Google Chrome if installed (better site compatibility); if no browser exists, chromium is auto-installed per-user (no admin rights, v1.2.1+)
- Viewport defaults to 1920×1200 for maximum content visibility
- Output is truncated when used as an agent tool to prevent token overflow
- Runs natively on Windows since v1.2.1 (named-pipe transport — no WSL), plus macOS and Linux
