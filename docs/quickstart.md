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
    max_iterations=10  # Default for general purpose agents
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

ConnectOnion tracks all agent behavior automatically:

```python
# See what your agent has been doing
print(agent.history.summary())
```

**Output:**

```
Agent: assistant
Total tasks: 3
Tools used: calculate (2), search (1), get_time (1)
Activity logged to: .co/logs/assistant.log
```

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
# Create with minimal template (default)
co create my-agent

# Create with playwright template
co create my-browser-bot --template playwright

# Initialize in existing directory
co init  # Adds .co folder only
co init --template playwright  # Adds full template
```

### What Gets Created

```
my-agent/
├── agent.py                                              # Main agent implementation
├── .env                                                  # API keys (auto-configured)
├── co-vibecoding-principles-docs-contexts-all-in-one.md  # Complete framework docs
├── .gitignore                                            # Git configuration
└── .co/                                                  # ConnectOnion metadata
    ├── config.toml
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
Make sure you:
1. Copied `.env.example` to `.env`
2. Added your actual API key
3. Are running from the project directory

### "Permission denied"
Ensure you have write permissions in the current directory.

### "Module not found"
Install ConnectOnion: `pip install connectonion`

---

**Need help?** Check our [examples](examples.md) or [join Discord](https://discord.gg/4xfD9k8AUF) for support.
