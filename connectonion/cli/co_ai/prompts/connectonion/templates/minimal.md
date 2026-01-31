# Minimal Template

The simplest starting point for learning ConnectOnion.

## Quick Start

```bash
co create my-bot --template minimal
cd my-bot
python agent.py
```

## What You Get

```
my-bot/
├── agent.py            # Agent with calculator tool
├── .env                # API keys
├── .co/
│   └── docs/           # ConnectOnion documentation
└── README.md           # Project docs
```

## Tools Included

| Tool | Description |
|------|-------------|
| `calculator(expression)` | Evaluate math expressions |

## Example Usage

```python
from connectonion import Agent

def calculator(expression: str) -> float:
    """Evaluate a math expression."""
    return eval(expression)

agent = Agent("assistant", tools=[calculator])
result = agent.input("What is 25 * 4?")
```

Interactive mode:

```
You: What is 15% of 200?
Agent: 15% of 200 is 30.0
```

## Use Cases

- Learning ConnectOnion basics
- Quick prototyping
- Template for custom agents
- Understanding tool calling

## Dependencies

- `connectonion`
- `python-dotenv`

## Customization

### Add More Tools

```python
def search(query: str) -> str:
    """Search for information."""
    return f"Results for: {query}"

agent = Agent(
    "assistant",
    tools=[calculator, search]
)
```

### Add System Prompt

Create `prompt.md`:

```markdown
# Assistant

You are a helpful assistant with calculation abilities.

## Guidelines
- Show your work
- Be precise with numbers
```

Then reference it:

```python
agent = Agent(
    "assistant",
    system_prompt="prompt.md",
    tools=[calculator]
)
```

## Next Steps

- [Tools](../concepts/tools.md) - Add custom tools
- [Prompts](../concepts/prompts.md) - Customize personality
- [Events](../concepts/events.md) - Add lifecycle hooks
