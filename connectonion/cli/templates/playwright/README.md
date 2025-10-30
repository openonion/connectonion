# Playwright Web Automation Agent

A powerful browser automation agent using Playwright. Demonstrates stateful browser control, web scraping, form filling, and interactive automation.

## Quick Start

```bash
# 1. Initialize project
co init --template playwright

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Run the agent
python agent.py
```

## What's Inside

**Stateful Browser Tools:**
- `start_browser()` - Launch browser instance
- `navigate()` - Go to URLs with smart waiting
- `scrape_content()` - Extract text from pages
- `take_screenshot()` - Capture page screenshots
- `fill_form()` - Fill and submit forms
- `click()` - Click elements
- `extract_links()` - Get all links from page
- `execute_javascript()` - Run custom JS
- `get_page_info()` / `get_session_info()` - Check browser state
- `close_browser()` - Clean up resources

## Interactive Mode

The agent supports interactive conversation for browser automation:

```bash
You: Start the browser and go to example.com
Agent: [Starts browser and navigates]

You: Take a screenshot
Agent: [Captures screenshot]

You: Extract all links from the page
Agent: [Lists all links found]
```

## Example Usage

```python
from connectonion import Agent

# The browser instance maintains state across tool calls
agent.input("Start the browser and navigate to example.com")
agent.input("Take a screenshot of the homepage")
agent.input("Extract all links that contain 'doc'")
agent.input("Close the browser")
```

## Key Features

### Stateful Session
- Browser state persists across tool calls
- Navigate multiple pages in one session
- Maintain cookies and session data

### Smart Automation
- Automatic waiting for page loads
- Error handling with helpful messages
- Screenshot and download tracking

### Flexible Input
- Natural language commands
- JSON form data for complex inputs
- CSS selectors for precise targeting

## Common Use Cases

**Web Scraping:**
```python
agent.input("Go to news.ycombinator.com and extract the top 5 article titles")
```

**Form Automation:**
```python
agent.input("Navigate to the contact form and fill it with name 'John' and email 'john@example.com'")
```

**Screenshot Documentation:**
```python
agent.input("Take full-page screenshots of example.com, github.com, and python.org")
```

**Link Extraction:**
```python
agent.input("Go to docs.python.org and extract all tutorial links")
```

## Tips

- Always `start_browser()` before other operations
- Use `get_session_info()` to check browser state
- Call `close_browser()` when done to free resources
- Screenshots are saved in the current directory
- Use headless=False to see browser in action

## Next Steps

**More Templates:**
- `co init --template minimal` - Simple calculator agent
- `co init --template web-research` - Web search tools
- `co init --template meta-agent` - Multi-agent orchestration

## Learn More

- [Playwright Documentation](https://playwright.dev/python/)
- [ConnectOnion Docs](https://docs.connectonion.com)
- [Discord Community](https://discord.gg/4xfD9k8AUF)
