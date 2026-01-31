# Playwright Template

Browser automation agent with full web control capabilities.

## Quick Start

```bash
co create browser-bot --template playwright
cd browser-bot
pip install playwright
playwright install chromium
python agent.py
```

## What You Get

```
browser-bot/
├── agent.py            # BrowserAutomation class with 11 tools
├── prompt.md           # Browser automation system prompt
├── requirements.txt    # playwright, connectonion, python-dotenv
├── .env                # API keys
├── .co/
│   └── docs/           # ConnectOnion documentation
└── README.md           # Project docs
```

## Tools Included

| Tool | Description |
|------|-------------|
| `start_browser(headless)` | Launch browser instance |
| `navigate(url, wait_until)` | Navigate to URL |
| `take_screenshot(filename, full_page)` | Capture screenshots |
| `scrape_content(selector)` | Extract text with CSS selectors |
| `fill_form(form_data)` | Fill form fields |
| `click(selector)` | Click elements |
| `extract_links(filter_pattern)` | Get all links from page |
| `wait_for_element(selector, timeout)` | Wait for DOM elements |
| `execute_javascript(script)` | Run custom JavaScript |
| `get_page_info()` | Get URL, title, viewport |
| `get_session_info()` | Get browser state |

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
       [Takes screenshot, scrapes content]
       Here are the top 5 stories:
       1. ...
```

## Use Cases

- Web scraping and data extraction
- Form automation
- Visual testing and screenshots
- Link crawling
- Dynamic content handling
- Browser-based testing

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

### Add Custom Selectors

```python
# The agent uses CSS selectors
result = agent.input("Click the button with class 'submit-btn'")
result = agent.input("Extract text from #main-content")
```

### Headless vs Visible Browser

```python
# Default is headless (no window)
result = agent.input("Start browser in headless mode")

# Or visible for debugging
result = agent.input("Start browser with headless=false")
```

### Wait Strategies

The `navigate` tool supports wait strategies:
- `load` - Wait for page load
- `domcontentloaded` - Wait for DOM ready
- `networkidle` - Wait for network to be idle

## Tips

- Browser maintains state across commands (stateful)
- Screenshots are saved to current directory
- Use CSS selectors for precise element targeting
- Agent tracks visited URLs and screenshots

## Next Steps

- [Playwright Docs](https://playwright.dev/python/) - Full Playwright API
- [Tools](../concepts/tools.md) - Add custom tools
- [XRay Debugging](../debug/xray.md) - Debug tool execution
