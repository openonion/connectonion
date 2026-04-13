# Minimal Template

The default starting point for a ConnectOnion agent. Includes file and shell tools plus browser automation.

## Quick Start

```bash
co create my-bot --template minimal
cd my-bot
python agent.py
```

## What You Get

```
my-bot/
├── agent.py            # Agent with file, shell, and browser tools
├── prompt.md           # System prompt
├── .env                # API keys
├── .co/
│   └── docs/           # ConnectOnion documentation
└── README.md           # Project docs
```

## Tools Included

| Tool | Description |
|------|-------------|
| `bash` | Run shell commands |
| `read_file` | Read file contents with line numbers |
| `edit` | Make precise edits to existing files |
| `glob` | Find files by pattern |
| `grep` | Search file contents by regex |
| `write` | Create or overwrite files |
| `BrowserAutomation` | Full browser control (navigate, click, screenshot, etc.) |

## Plugins Included

| Plugin | Purpose |
|--------|---------|
| `image_result_formatter` | Format browser screenshots for vision models |
| `tool_approval` | Web-based approval for tool calls |

## Example Usage

```python
from connectonion import Agent, bash, read_file, edit, glob, grep, write
from connectonion.useful_tools.browser_tools import BrowserAutomation
from connectonion.useful_plugins import image_result_formatter, tool_approval

browser = BrowserAutomation(headless=True)

agent = Agent(
    name="my-agent",
    system_prompt="prompt.md",
    tools=[bash, read_file, edit, glob, grep, write, browser],
    plugins=[image_result_formatter, tool_approval],
    model="co/gemini-2.5-pro",
)

result = agent.input("what is your task?")
print(result)
```

Interactive mode:

```
You: What files are in the current directory?
Agent: [runs bash ls command]
       Here are the files: ...
```

## Use Cases

- General-purpose automation (file editing, shell commands, web browsing)
- Starting point for customizing a new agent
- Projects that need both local file access and web capabilities

## Dependencies

- `connectonion`
- `playwright` (for browser tools)
- `python-dotenv`

After installing, run:
```bash
playwright install chromium
```

## Customization

### Add Custom Tools

```python
def my_tool(query: str) -> str:
    """Do something specific."""
    return f"Result: {query}"

agent = Agent(
    name="my-agent",
    system_prompt="prompt.md",
    tools=[bash, read_file, edit, glob, grep, write, browser, my_tool],
    plugins=[image_result_formatter, tool_approval],
    model="co/gemini-2.5-pro",
)
```

### Headless vs Visible Browser

```python
# Headless (background, default in template)
browser = BrowserAutomation(headless=True)

# Visible (show browser window, useful for debugging)
browser = BrowserAutomation(headless=False)
```

## Next Steps

- [Tools](../concepts/tools.md) - Add custom tools
- [Prompts](../concepts/prompts.md) - Customize personality
- [Events](../concepts/events.md) - Add lifecycle hooks
