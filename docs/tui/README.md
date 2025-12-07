# TUI Components

Terminal UI components for interactive agent interfaces.

## Quick Reference

| Component | Purpose | Import |
|-----------|---------|--------|
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
from connectonion.tui import pick, Input, StatusBar
from rich.console import Console

console = Console()

# Single-select menu
choice = pick(
    "Select model:",
    ["gpt-4", "claude-3", "gemini-pro"]
)

# Text input with file autocomplete
from connectonion.tui import FileProvider
text = Input(triggers={"@": FileProvider()}).run()

# Status bar
status = StatusBar([
    ("model", "gpt-4", "magenta"),
    ("tokens", "1.2k", "green"),
])
console.print(status.render())
```

## Architecture

```
User Input → TUI Component → Terminal (Rich) → User
     ↑                              ↓
     └──── Keyboard Events ────────┘
```

Components use:
- **Rich** for terminal rendering
- **Raw mode** for keyboard capture
- **ANSI codes** for styling
