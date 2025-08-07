# Getting Started

Build your first AI agent in 60 seconds.

## Install

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="your-key-here"
```

## Your First Agent

```python
from connectonion import Agent

# Define what your agent can do
def calculate(expression: str) -> str:
    """Do math calculations."""
    return str(eval(expression))

# Create your agent
agent = Agent("assistant", tools=[calculate])

# Use it!
result = agent.run("What is 42 * 17?")
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
    tools=[calculate, search, get_time]
)

# It can use multiple tools in one request!
result = agent.run("Search for Python tutorials and tell me what time it is")
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

result = agent.run("Hello!")
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
assistant = Agent("file_helper", tools=[write_file, read_file])

# Use it
assistant.run("Save 'Hello World' to greeting.txt")
assistant.run("What's in greeting.txt?")
```

## Next Steps

Ready for more?

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