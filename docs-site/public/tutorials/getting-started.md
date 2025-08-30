# Getting Started

Build your first AI agent in 60 seconds.

## Install

```bash
pip install connectonion
```

## Quick Start with CLI

The fastest way to start is with the ConnectOnion CLI:

```bash
# Create a directory for your meta-agent
mkdir meta-agent
cd meta-agent

# Initialize the meta-agent
co init

# Copy .env.example to .env and add your OpenAI API key
cp .env.example .env
# Edit .env and add your key

# Run your meta-agent
python agent.py
```

That's it! You now have a self-reflective meta-agent with planning capabilities. 🎉

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
History saved to: ~/.connectonion/agents/assistant/behavior.json
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
# Meta-agent (default) - ConnectOnion development assistant
co init

# Web automation with Playwright
co init --template playwright
```

### What Gets Created

```
my-project/
├── agent.py           # Main agent implementation
├── prompts/           # System prompts (meta-agent only)
│   ├── metagent.md
│   ├── docs_retrieve_prompt.md
│   ├── answer_prompt.md
│   └── think_prompt.md
├── prompt.md          # System prompt (playwright only)
├── README.md          # Project documentation (meta-agent only)
├── .env.example       # Environment variables template
└── .co/               # ConnectOnion metadata
    ├── config.toml
    └── docs/
        └── connectonion.md  # Embedded framework documentation
```

Learn more about templates in the [Templates Documentation](templates.md).

## Next Steps

Ready for more?

- **[CLI Reference](cli.md)** - All CLI commands and options
- **[Templates](templates.md)** - Pre-built agent templates
- **[Core Concepts](concepts.md)** - How agents and tools work
- **[Examples](examples.md)** - Copy-paste ready code
- **[API Reference](api.md)** - Detailed documentation

## Quick Tips

1. **Functions = Tools** (no classes needed!)
2. **Docstrings = Descriptions** (agent reads these)
3. **Type hints = Better results** (helps agent understand)
4. **History = Free** (automatic tracking)

---

**Need help?** Check our [examples](examples.md) or [join the waitlist](https://connectonion.com) for support.
