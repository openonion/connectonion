# Quick Start

Build your first AI agent in 60 seconds.

## Install

```bash
pip install connectonion
```

## Quick Start with CLI

The fastest way to start is with the ConnectOnion CLI:

```bash
# Create a new agent project
co create my-agent

# Navigate to the project
cd my-agent

# Run your agent (API key setup is automatic!)
python agent.py
```

That's it! You now have a working agent ready to use. 🎉

## Manual Setup (Alternative)

```python
from connectonion import Agent

# Define what your agent can do
def calculate(expression: str) -> str:
    """Do math calculations."""
    return str(eval(expression))

# Create your agent
agent = Agent(
    "assistant", 
    tools=[calculate],
    max_iterations=5  # Simple calculations don't need many iterations
)

# Use it!
result = agent.input("What is 42 * 17?")
print(result)
```

**Output:**

```
To calculate 42 * 17, I'll use the calculator tool.

The result is 714.
```

That's it! You just built an AI agent that can use tools. 🎉

## Add More Tools

Want your agent to do more? Just add more functions:

```python
def search(query: str) -> str:
    """Search the web."""
    return f"Results for {query}: [simulated results]"

def get_time() -> str:
    """Get current time."""
    from datetime import datetime
    return datetime.now().strftime("%I:%M %p")

# Create a more capable agent
agent = Agent(
    name="assistant",
    tools=[calculate, search, get_time],
    max_iterations=100  # Default for general purpose agents
)

# It can use multiple tools in one request!
result = agent.input("Search for Python tutorials and tell me what time it is")
print(result)
```

## Make It Yours

Give your agent a personality with flexible system prompts:

```python
# Option 1: Direct string
agent = Agent(
    name="friendly_bot",
    system_prompt="You are a cheerful assistant who loves to help!",
    tools=[calculate, search, get_time]
)

# Option 2: Load from file (auto-detected)
agent = Agent(
    name="expert_bot",
    system_prompt="prompts/expert.md",  # Loads from file
    tools=[calculate, search, get_time]
)

# Option 3: Using Path object
from pathlib import Path
agent = Agent(
    name="custom_bot",
    system_prompt=Path("prompts/custom_personality.txt"),
    tools=[calculate, search, get_time]
)

result = agent.input("Hello!")
# Response will reflect the personality defined in your prompt
```

## Track Everything (Automatic!)

ConnectOnion tracks all agent behavior automatically to `.co/logs/{name}.log` and `.co/evals/`:

```python
# Check token usage after a task
result = agent.input("What is 42 * 17?")
print(f"Cost: ${agent.total_cost:.4f}")
print(f"Context used: {agent.context_percent:.1f}%")
```

All sessions are also saved as YAML in `.co/evals/` for evaluation and replay.

## Real Example

Here's a practical agent in ~10 lines:

```python
from connectonion import Agent

def write_file(filename: str, content: str) -> str:
    """Save content to a file."""
    with open(filename, 'w') as f:
        f.write(content)
    return f"Saved to {filename}"

def read_file(filename: str) -> str:
    """Read a file."""
    with open(filename, 'r') as f:
        return f.read()

# Create a file assistant
assistant = Agent(
    "file_helper", 
    tools=[write_file, read_file],
    max_iterations=8  # File operations are usually straightforward
)

# Use it
assistant.input("Save 'Hello World' to greeting.txt")
assistant.input("What's in greeting.txt?")
```

## CLI Templates

ConnectOnion provides different templates for common use cases:

```bash
# Create with minimal template (default - includes file tools + browser)
co create my-agent

# Create with coder template (bash + file editing, no browser)
co create my-coder --template coder

# Create with browser template (dedicated browser automation)
co create my-browser-bot --template browser

# Or drive one persistent, logged-in browser straight from the shell — no project:
#   co browser go_to example.com
#   co browser do "log in and download my invoices"
# See co-browser.md for the full command reference and multi-agent tabs.

# Create with web-research template
co create my-researcher --template web-research

# Initialize in existing directory
co init  # Adds .co folder only
co init --template coder  # Adds full template
```

## Your Own Mail and Files

Your agent can work on **your** Gmail, Outlook, and Google Drive — one
authorization, then plain commands. Useful from the terminal too, not just
inside an agent:

```bash
co auth google                          # once, opens the browser

co gmail                                # your inbox, numbered
co gmail read 3                         # open #3
co gmail send bob@example.com "Hi" "Body text"
co gmail search "from:alice@example.com is:unread"

co gdrive                               # 20 most recently modified files
co gdrive get 3 --to ~/Downloads        # download #3
co gdrive put report.pdf                # upload
```

Numbers mean your last listing — `read 3` opens row 3 of the table you just
saw. `co auth microsoft` gives you the same thing for Outlook, plus contacts.

The same access is available to agents:

```python
from connectonion import Agent, Gmail, GDrive

agent = Agent("assistant", tools=[Gmail(), GDrive()])
agent.input("Any unread mail from Alice? If so, find her latest file in my Drive.")
```

See [`co gmail`](cli/gmail.md), [`co gdrive`](cli/gdrive.md), and
[`co outlook`](cli/outlook.md).

## Copy & Customize Built-in Tools

Want to customize a built-in tool? Copy it to your project:

```bash
# See what's available
co copy --list

# Copy a tool to ./tools/
co copy Gmail

# Copy a plugin to ./plugins/
co copy re_act

# Copy multiple items
co copy Gmail Shell memory
```

Then import from your local copy instead:

```python
# Before (from package)
from connectonion import Gmail

# After (from your copy)
from tools.gmail import Gmail  # Now you can customize it!
```

### What Gets Created

```
my-agent/
├── agent.py                                              # Main agent implementation
├── .env                                                  # API keys (auto-configured)
├── co-vibecoding-principles-docs-contexts-all-in-one.md  # Complete framework docs
├── .gitignore                                            # Git configuration
└── .co/                                                  # ConnectOnion metadata
    ├── host.yaml
    └── docs/
        └── co-vibecoding-principles-docs-contexts-all-in-one.md
```

Learn more about templates in the [Templates Documentation](templates/).

## Next Steps

Ready for more?

- **[CLI Reference](cli/)** - All CLI commands and options
- **[Templates](templates/)** - Pre-built agent templates
- **[Agent Guide](concepts/agent.md)** - How agents work
- **[Tools Guide](concepts/tools.md)** - How tools work
- **[Examples](examples.md)** - Copy-paste ready code
- **[API Reference](api.md)** - Detailed documentation

## Quick Tips

1. **Functions = Tools** (no classes needed!)
2. **Docstrings = Descriptions** (agent reads these)
3. **Type hints = Better results** (helps agent understand)
4. **Logging = Free** (automatic activity tracking to `.co/logs/`)

---

## Troubleshooting

### "API key not found"
Use the CLI flow first:

```bash
co auth
co status
```

If the key still is not found, run `co keys` to see which `.env` or `~/.co/keys.env` file is being loaded. For manual setup, set `OPENONION_API_KEY` for `co/` models or the provider-specific key such as `OPENAI_API_KEY` for direct provider models.

### "Permission denied"
Ensure you have write permissions in the current directory.

### "Module not found"
Install ConnectOnion: `pip install connectonion`

---

**Need help?** Check our [examples](examples.md) or [join Discord](https://discord.gg/4xfD9k8AUF) for support.
