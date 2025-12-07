# Input

Smart text input with trigger-based autocomplete.

## Quick Start

```python
from connectonion.tui import Input

# Simple input
text = Input().run()

# With file autocomplete
from connectonion.tui import FileProvider
text = Input(triggers={"@": FileProvider()}).run()
```

## Features

### Trigger Autocomplete

```python
from connectonion.tui import Input, FileProvider, StaticProvider

# @ triggers file browser
text = Input(triggers={"@": FileProvider()}).run()
# User types: "edit @src/" → shows file dropdown

# / triggers command palette
commands = StaticProvider([("/today", "/today"), ("/inbox", "/inbox")])
text = Input(triggers={"/": commands}).run()
```

### Hints and Tips

```python
text = Input(
    hints=["/ commands", "@ files", "Enter submit"],
    tips=["Try /today for briefing", "Join Discord!"],
    divider=True,
).run()
```

## API

```python
Input(
    prompt: str = None,       # Custom prompt text
    triggers: dict = None,    # {char: Provider} for autocomplete
    hints: list[str] = None,  # Always-visible hints
    tips: list[str] = None,   # Rotating tips
    divider: bool = False,    # Add horizontal dividers
    max_visible: int = 8,     # Max dropdown items
    console: Console = None,
    style: str = "modern",    # "modern", "minimal", "classic"
).run() -> str
```

## Styles

- **modern** - Magenta prompt, clean design
- **minimal** - Bare bones, no decorations
- **classic** - Traditional input style
