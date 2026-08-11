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
1. Uses live `agent.io` when a frontend is connected.
2. Otherwise returns `NOT ANSWERED` immediately by default.
3. If the operator explicitly enables email fallback, sends one escaped,
   correlated question to the configured contact and waits for a bounded reply.
4. Returns the answer, or a fail-closed `NOT ANSWERED` result.

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

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `question` | `str` | Yes | The question to ask |
| `options` | `list[str]` | Yes | List of choices for the user to select from |
| `multi_select` | `bool` | No | Allow multiple selections (default: False) |

## Examples

```python
# Single choice
color = ask_user("Pick a color", options=["Red", "Green", "Blue"])

# Multiple choice
languages = ask_user(
    "Which languages do you know?",
    options=["Python", "JavaScript", "Rust", "Go"],
    multi_select=True
)

# Yes/No
confirm = ask_user("Proceed with deployment?", options=["Yes", "No"])
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

- Live mode requires `agent.io`; the frontend handles the `ask_user` event.
- Unattended email is opt-in: set `CONNECTONION_ASK_USER_EMAIL=1` and
  `OWNER_EMAIL=you@example.com`. The machine-global `~/.co/keys.env` contact
  wins over a conflicting project `.env` value.
- Optional bounded settings are
  `CONNECTONION_ASK_USER_EMAIL_TIMEOUT_SECONDS` (1–900, default 900) and
  `CONNECTONION_ASK_USER_EMAIL_POLL_SECONDS` (0.1–60, default 20).
- Email replies answer non-sensitive choice questions only; free-form fields
  and replies outside the offered choices are rejected. They never grant
  Host/ACP tool permissions. Passwords, secrets, tokens, OTPs, verification
  codes, and common secret-shaped values are rejected before sending because
  received mail is persisted.
- The email backend must confirm that it applied the exact server-side subject
  filter. Older deployments that silently ignore the filter fail closed.
