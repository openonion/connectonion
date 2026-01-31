# ask_user

Ask the user a question during agent execution via connection.

## Usage

**Option 1: Import directly**

```python
from connectonion.useful_tools import ask_user

agent = Agent("assistant", tools=[ask_user])
```

**Option 2: Copy and customize**

```bash
co copy ask_user
```

```python
from tools.ask_user import ask_user  # Your local copy

agent = Agent("assistant", tools=[ask_user])
```

## Quick Start

```python
from connectonion.useful_tools import ask_user

agent = Agent("assistant", tools=[ask_user])
agent.input("Help me choose a programming language")
# Agent can now ask user questions mid-execution
```

## How It Works

When the agent calls `ask_user`, it:
1. Sends an `ask_user` event via `agent.connection`
2. Waits for user response
3. Returns the answer to the agent

```
Agent calls ask_user("What color?", ["red", "blue"])
    ↓
connection.send({ type: "ask_user", question: "...", options: [...] })
    ↓
connection.receive() ← waits for response
    ↓
Returns answer to agent
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `question` | `str` | The question to ask |
| `options` | `list[str]` | Optional list of choices |
| `multi_select` | `bool` | Allow multiple selections (default: False) |

## Examples

```python
# Free-form question
answer = ask_user("What is your project name?")

# Single choice
color = ask_user("Pick a color", options=["Red", "Green", "Blue"])

# Multiple choice
languages = ask_user(
    "Which languages do you know?",
    options=["Python", "JavaScript", "Rust", "Go"],
    multi_select=True
)
```

## Frontend Integration

The frontend receives this event:

```json
{
  "type": "ask_user",
  "question": "Pick a color",
  "options": ["Red", "Green", "Blue"],
  "multi_select": false
}
```

And responds with:

```json
{
  "answer": "Blue"
}
```

## Requirements

- Requires `agent.connection` to be set (works with hosted agents)
- Frontend must handle `ask_user` event type
