# TUI Components

Terminal UI components for interactive agent interfaces.

## Quick Reference

| Component | Purpose | Import |
|-----------|---------|--------|
| [Chat](chat.md) | Full chat interface with agent | `from connectonion.tui import Chat` |
| [Input](input.md) | Text input with autocomplete | `from connectonion.tui import Input` |
| [pick](pick.md) | Single-select menu | `from connectonion.tui import pick` |
| [Dropdown](dropdown.md) | Dropdown menus | `from connectonion.tui import Dropdown` |
| [StatusBar](status_bar.md) | Powerline-style status | `from connectonion.tui import StatusBar` |
| [Footer](footer.md) | Footer with help text | `from connectonion.tui import Footer` |
| [Divider](divider.md) | Visual dividers | `from connectonion.tui import Divider` |
| [fuzzy](fuzzy.md) | Fuzzy matching | `from connectonion.tui import fuzzy_match` |
| [keys](keys.md) | Keyboard input | `from connectonion.tui import getch` |
| [providers](providers.md) | Autocomplete data sources | `from connectonion.tui import FileProvider` |

## Quick Start

```python
from connectonion import Agent
from connectonion.tui import Chat

# Create agent
agent = Agent("assistant", tools=[...])

# Launch chat interface
chat = Chat(
    agent=agent,
    title="My Assistant",
    welcome="Hello! How can I help?",
    hints=["/ commands", "Enter send", "Ctrl+D quit"],
)
chat.run()
```

## Customizing Components

Need to modify a TUI component? Copy it to your project:

```bash
# Copy Chat interface to ./tui/
co copy chat

# Copy other components
co copy chat fuzzy dropdown

# See all available
co copy --list
```

Then import from your local copy:

```python
# Before (from package)
from connectonion.tui import Chat

# After (from your copy)
from tui.chat import Chat  # Customize freely!
```

## Chat Features

The `Chat` component includes:
- **Status bar** - Agent name, status, model, tokens, cost
- **Message history** - Scrollable conversation
- **Thinking indicator** - Shows LLM thinking and tool calls
- **Autocomplete** - Trigger-based (/, @) command completion
- **Input locking** - Prevents multiple submissions

### Thinking Indicator

Shows real-time progress:

```
⠹ Thinking... 5s (usually 3-10s)    # During LLM call

⠹ Search emails in inbox            # During tool call
  └─ search_emails("aaron")
```

## Architecture

```
User Input → TUI Component → Terminal (Rich/Textual) → User
     ↑                              ↓
     └──── Keyboard Events ────────┘
```

Components use:
- **Textual** for full interactive apps (Chat)
- **Rich** for simple terminal rendering
- **Raw mode** for keyboard capture
