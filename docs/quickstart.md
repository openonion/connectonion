# Quick Start Guide

Get up and running with ConnectOnion in under 2 minutes.

## 1. Install ConnectOnion

```bash
pip install connectonion
```

## 2. Create Your First Meta-Agent

```bash
# Create a new directory for your agent
mkdir meta-agent
cd meta-agent

# Initialize the meta-agent (default)
co init
```

This creates a ConnectOnion development assistant with powerful capabilities:
- `agent.py` - Meta-agent with documentation expertise and development tools
- `prompt.md` - System prompt for your agent
- `.env.example` - Template for API keys
- `.co/docs/` - Embedded ConnectOnion documentation for offline reference

## 3. Set Up Your API Key

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:
```
OPENAI_API_KEY=sk-your-actual-api-key-here
```

## 4. Run Your Agent

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

## Choose a Different Template

ConnectOnion offers specialized templates:

### Playwright Agent (Web Automation)
```bash
co init --template playwright
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