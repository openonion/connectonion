# Browser Template

Browser automation agent with full web control capabilities.

## Quick Start

```bash
co create browser-bot --template browser
cd browser-bot
pip install playwright
playwright install chromium
python agent.py
```

## What You Get

```
browser-bot/
├── agent.py            # BrowserAutomation agent with all tools
├── prompts/
│   └── agent.md        # Browser automation system prompt
├── requirements.txt    # playwright, connectonion, python-dotenv
├── .env                # API keys
├── .co/
│   └── docs/           # ConnectOnion documentation
└── README.md           # Project docs
```

## Tools Included

All tools from `BrowserAutomation`:

| Tool | Description |
|------|-------------|
| `go_to(url)` | Navigate to URL (auto-adds https://) |
| `take_screenshot(path, full_page)` | Capture screenshots, returns base64 |
| `click(description)` | Click element by natural language description |
| `hover(description)` | Hover over element (for menus, tooltips) |
| `mouse_click(x, y)` | Click at exact screen coordinates |
| `right_click(description)` | Right-click to open context menus |
| `double_click(description)` | Double-click on element |
| `keyboard_type(text)` | Type text into focused element |
| `keyboard_press(key)` | Press key or shortcut (Enter, Control+Enter, etc.) |
| `get_system_info()` | Get OS info for platform-aware shortcuts |
| `get_text()` | Get all visible text from the page |
| `get_current_url()` | Get current page URL |
| `get_links_from_page(filter)` | Extract all links, optional filter |
| `scroll(times, description)` | Scroll page or specific element |
| `select_option(field, option)` | Select dropdown option |
| `check_checkbox(description, checked)` | Check or uncheck checkbox |
| `wait(seconds)` | Wait for specified seconds |
| `wait_for_element(description)` | Wait for element to appear |
| `wait_for_text(text)` | Wait for text on page |
| `wait_for_manual_login(site)` | Pause for manual 2FA/login |
| `set_viewport(width, height)` | Set browser window size |

## Example Usage

```python
# Scrape a webpage
result = agent.input("Go to example.com and extract the main heading")

# Fill a form
result = agent.input('Fill the contact form with name "John" and email "john@example.com"')

# Take screenshots
result = agent.input("Take a full-page screenshot of the documentation site")

# Extract links
result = agent.input("Get all PDF links from the downloads page")
```

Interactive mode:

```
You: Go to hacker news and get the top 5 stories
Agent: I'll navigate to Hacker News and extract the top stories...
       Here are the top 5 stories:
       1. ...
```

## Use Cases

- Web scraping and data extraction
- Form automation
- Visual testing and screenshots
- Link crawling
- Dynamic content handling
- Social media automation (hover menus, reactions)

## Dependencies

```
connectonion
playwright
python-dotenv
```

After installing, run:
```bash
playwright install chromium
```

## Customization

### Headless vs Visible Browser

```python
# Default in BrowserAutomation is visible (headless=False)
browser = BrowserAutomation()

# Template creates it headless (background mode)
browser = BrowserAutomation(headless=True)

# Override for debugging
browser = BrowserAutomation(headless=False)
```

### Keyboard Shortcuts

```python
# Get OS info first for correct modifier key
browser.get_system_info()  # → "OS: macOS. Use Meta for shortcuts..."

# macOS
browser.keyboard_press("Meta+a")   # Select all
browser.keyboard_press("Meta+c")   # Copy

# Windows/Linux
browser.keyboard_press("Control+a")
browser.keyboard_press("Control+c")
```

### Hover Menus

```python
# Hover to reveal reaction picker or dropdown
browser.hover("the Like button")
browser.take_screenshot()           # See the hover menu
browser.mouse_click(x, y)          # Click specific item by coordinates
```

## Notes

- Browser maintains state across commands (stateful)
- Screenshots are saved to `.tmp/` directory
- Persistent profile at `~/.co/browser_profile/` (survives restarts)
- Uses Google Chrome if installed (better site compatibility), falls back to Chromium
- Element finding uses a vision LLM — describe what you see, not a CSS selector

## Next Steps

- [Browser Tools Docs](../useful_tools/browser_tools.md) - Full BrowserAutomation API
- [Tools](../concepts/tools.md) - Add custom tools
- [XRay Debugging](../debug/xray.md) - Debug tool execution
