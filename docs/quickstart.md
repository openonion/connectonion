# Quick Start Guide

Get up and running with ConnectOnion in under 2 minutes.

## 1. Install ConnectOnion

```bash
pip install connectonion
```

## 2. Create Your First Agent

```bash
# Create a new agent project
co create my-agent

# Navigate to the project
cd my-agent
```

This creates a minimal agent with everything you need:
- `agent.py` - Ready-to-run agent with example tools
- `.env` - API keys (set up during creation)
- `.co/` - Configuration and embedded ConnectOnion documentation
- `.gitignore` - Pre-configured to exclude sensitive files
- `co-vibecoding-principles-docs-contexts-all-in-one.md` - Complete framework docs

*The CLI guides you through API key setup automatically!*

## 3. Run Your Agent

```bash
python agent.py
```

Your meta-agent comes with powerful built-in tools:
- **answer_connectonion_question()** - Expert answers from embedded docs
- **create_agent_from_template()** - Generate complete agent code
- **generate_tool_code()** - Create tool functions
- **create_test_for_agent()** - Generate pytest test suites
- **think()** - Self-reflection to analyze task completion
- **generate_todo_list()** - Create structured plans (uses GPT-4o-mini)
- **suggest_project_structure()** - Architecture recommendations

## Try These Commands

Once your meta-agent is running, try these:

```python
# Learn about ConnectOnion
result = agent.input("What is ConnectOnion and how do tools work?")

# Generate agent code
result = agent.input("Create a web scraper agent")

# Create tool functions
result = agent.input("Generate a tool for sending emails")

# Get project structure advice
result = agent.input("Suggest structure for a multi-agent system")

# Generate a structured plan
result = agent.input("Create a to-do list for building a REST API")
```

## 🔍 Debug Your Agent Interactively

ConnectOnion includes powerful interactive debugging with `@xray` breakpoints:

```python
from connectonion import Agent
from connectonion.decorators import xray

# Mark tools you want to debug
@xray
def search_data(query: str) -> str:
    """Search for information."""
    return f"Found results for: {query}"

# Create agent
agent = Agent(
    name="debug_demo",
    tools=[search_data]
)

# Start interactive debugging
agent.auto_debug()
```

**What you'll see at each `@xray` breakpoint:**

```
@xray BREAKPOINT: search_data

Local Variables:
  query = "Python tutorials"
  result = "Found results for: Python tutorials"

What do you want to do?
  → Continue execution       [c or Enter]
    Edit values (Python)     [e]
    Quit debugging          [q]
>
```

**Try it now:**
```bash
# Run the included debug demo
cd simple-agent/
python agent_debug.py
```

**What you can do:**
- **Continue** (`c` or Enter): Resume execution
- **Edit** (`e`): Open Python REPL to modify variables
- **Quit** (`q`): Stop debugging

Perfect for:
- Understanding agent decisions
- Testing edge cases
- Exploring "what if" scenarios
- Learning how agents work

[Full debugging guide](auto_debug.md)

## Choose a Different Template

ConnectOnion offers specialized templates:

### Playwright Agent (Web Automation)
```bash
co create my-browser-bot --template playwright
cd my-browser-bot
```

Perfect for:
- Web scraping and data extraction
- Browser automation and testing
- Form filling and submission
- Screenshot capture
- Link crawling

Comes with stateful browser tools:
- `start_browser()` - Launch browser instance
- `navigate()` - Go to URLs
- `scrape_content()` - Extract page content
- `fill_form()` - Fill and submit forms
- `take_screenshot()` - Capture pages
- And many more browser automation tools

Note: Requires `pip install playwright && playwright install`

## What's Next?

### Customize Your Agent

Edit `prompt.md` to change your agent's personality:

```markdown
# Expert Assistant

You are a knowledgeable expert who provides detailed, accurate information.

## Your Style
- Professional and thorough
- Use examples to illustrate points
- Cite sources when possible
```

### Add Custom Tools

Add any Python function as a tool:

```python
# In agent.py
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email to someone."""
    # Your email logic here
    return f"Email sent to {to}"

# Add to your agent
agent = Agent(
    name="my_agent",
    system_prompt="prompt.md",
    tools=[answer_connectonion_question, think, send_email]  # Mix built-in and custom
)
```

### Explore More

- [CLI Reference](cli.md) - All CLI commands
- [Templates Guide](templates.md) - Template details
- [Tools Documentation](tools.md) - Creating tools
- [Examples](examples.md) - Full examples

## Troubleshooting

### "API key not found"
Make sure you:
1. Copied `.env.example` to `.env`
2. Added your actual OpenAI API key
3. Are running from the project directory

### "Permission denied"
Ensure you have write permissions in the current directory.

### "Module not found"
Install ConnectOnion: `pip install connectonion`

## Get Help

- [Documentation](https://github.com/connectonion/connectonion)
- [Join Waitlist](https://connectonion.com) for support
- [Report Issues](https://github.com/connectonion/connectonion/issues)