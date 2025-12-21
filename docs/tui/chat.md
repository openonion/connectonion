# Chat

Full-featured terminal chat interface for AI agents.

## Quick Start

```python
from connectonion import Agent
from connectonion.tui import Chat

agent = Agent("assistant", tools=[search, analyze])

chat = Chat(agent=agent)
chat.run()
```

## Installation

```bash
pip install connectonion[tui]
# or
pip install textual textual-autocomplete
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `agent` | Agent | ConnectOnion agent instance |
| `handler` | Callable | Custom message handler (alternative to agent) |
| `title` | str | Window title |
| `welcome` | str | Welcome message (markdown supported) |
| `hints` | list[str] | Footer hints like `["/ commands", "Enter send"]` |
| `triggers` | dict | Autocomplete triggers (see below) |
| `on_error` | Callable | Custom error handler |

## Autocomplete Triggers

Add command or mention autocomplete:

```python
from connectonion.tui import Chat, CommandItem
from textual_autocomplete import DropdownItem

chat = Chat(
    agent=agent,
    triggers={
        "/": [
            CommandItem(main="/help", prefix="?", id="/help"),
            CommandItem(main="/clear", prefix="⌫", id="/clear"),
            CommandItem(main="/quit", prefix="→", id="/quit"),
        ],
        "@": [
            DropdownItem(main="John", id="@john@example.com"),
            DropdownItem(main="Jane", id="@jane@example.com"),
        ],
    }
)
```

## Custom Commands

Register slash command handlers:

```python
chat = Chat(agent=agent)

@chat.command("/help")
def show_help(text):
    return "Available commands: /help, /clear, /quit"

@chat.command("/clear")
def clear_chat(text):
    # Clear logic
    return "Chat cleared"

chat.run()
```

## Status Bar

Shows real-time information:

```
🤖 Assistant    ◐ Thinking (1/10)    co/gpt-4  1,234 tok  $0.0012
```

- **Left**: Agent name
- **Center**: Current status with iteration
- **Right**: Model, token count, cost

## Thinking Indicator

Visual feedback during processing:

```
⠹ Thinking... 5s (usually 3-10s)
```

During tool execution:

```
⠹ Search emails in inbox
  └─ search_emails("aaron")
```

Shows:
- Description (what's happening)
- Function call (technical detail)

## Customizing

Copy and modify:

```bash
co copy chat
```

Then edit `./tui/chat.py`:

```python
from tui.chat import Chat, ThinkingIndicator

# Customize ThinkingIndicator
class MyThinkingIndicator(ThinkingIndicator):
    frames = ["◐", "◓", "◑", "◒"]  # Custom spinner

# Use in your Chat subclass
```

## Example: Gmail Agent

```python
from connectonion import Agent
from connectonion.tui import Chat, CommandItem
from connectonion.useful_tools import Gmail

gmail = Gmail()
agent = Agent("gmail-agent", tools=[gmail])

chat = Chat(
    agent=agent,
    title="Gmail Agent",
    welcome="**Gmail Assistant**\n\nI can search, read, and send emails.",
    hints=["/ commands", "@ mentions", "Enter send"],
    triggers={
        "/": [
            CommandItem(main="/inbox", prefix="📥", id="/inbox"),
            CommandItem(main="/sent", prefix="📤", id="/sent"),
            CommandItem(main="/compose", prefix="✏️", id="/compose"),
        ]
    }
)

chat.run()
```

## Widgets

Chat includes these widgets (all exported):

| Widget | Purpose |
|--------|---------|
| `ChatStatusBar` | Top status bar |
| `HintsFooter` | Bottom hints |
| `WelcomeMessage` | Initial welcome |
| `UserMessage` | User message bubble |
| `AssistantMessage` | Agent response |
| `ThinkingIndicator` | Processing animation |
| `TriggerAutoComplete` | Trigger-based autocomplete |

Import individually:

```python
from connectonion.tui import (
    Chat,
    ChatStatusBar,
    ThinkingIndicator,
    TriggerAutoComplete,
)
```
