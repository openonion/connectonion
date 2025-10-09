# Browser Agent - Web Automation with ConnectOnion

A simple browser automation agent powered by ConnectOnion and Playwright.

## 🚀 Quick Start

1. **Install dependencies**:
   ```bash
   pip install connectonion playwright python-dotenv
   playwright install  # Install browser drivers
   ```

2. **Set up environment**:
   ```bash
   # Add your OpenAI API key to .env
   echo "OPENAI_API_KEY=your-api-key-here" >> .env
   ```

3. **Run the agent**:
   ```bash
   python agent.py
   ```

## 📁 Project Structure

```
browser-agent/
├── agent.py                    # Main browser agent
├── demo.py                     # Interactive demo script
├── prompts/
│   └── browser_agent.md        # Agent system prompt
└── .env                        # Environment variables (create this)
```

## 🛠 Available Tools

The browser agent provides these automation capabilities:

- `start_browser()` - Launch Chromium browser
- `navigate()` - Go to any URL
- `take_screenshot()` - Capture screenshots with custom sizes
- `scrape_content()` - Extract text from pages
- `extract_links()` - Get all links from a page
- `set_viewport_size()` - Adjust browser window size
- `close_browser()` - Clean up browser session

## 💡 Example Usage

```python
# Interactive mode
python agent.py

# Example commands:
"Navigate to https://docs.connectonion.com and take a screenshot"
"Extract all links from the current page"
"Take a full-page screenshot and save it as docs.png"
```

## 🎯 Run the Demo

Try the automated demo that showcases all features:

```bash
python demo.py
```

This will:
1. Navigate to docs.connectonion.com
2. Take screenshots
3. Extract content and links
4. Navigate between pages
5. Clean up automatically

## 📝 How It Works

This example demonstrates ConnectOnion's class-based tool pattern:

```python
# The browser class maintains state across tool calls
browser = BrowserAutomation()

# Pass the class instance directly - ConnectOnion auto-discovers all methods!
agent = Agent(
    name="browser_agent",
    system_prompt="prompts/browser_agent.md",
    tools=[browser],  # Clean and simple!
    model="gpt-4o-mini"
)
```

ConnectOnion automatically:
- Discovers all public methods from the class
- Converts them to agent tools with proper schemas
- Maintains shared state (browser session) across calls
- Handles type hints and docstrings for the LLM

## 🔗 Resources

- [ConnectOnion Documentation](https://docs.connectonion.com)
- [GitHub Repository](https://github.com/openonion/connectonion)
- [Discord Community](https://discord.gg/4xfD9k8AUF)