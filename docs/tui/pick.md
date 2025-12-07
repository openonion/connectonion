# pick

Single-select menu with keyboard navigation.

## Quick Start

```python
from connectonion.tui import pick

choice = pick("Pick a color", ["Red", "Green", "Blue"])
# Press 1 → "Red", 2 → "Green", 3 → "Blue"
# Or use arrow keys + Enter
```

## Options

### Simple List

```python
choice = pick("Select model", ["gpt-4", "claude-3", "gemini"])
# Returns: "gpt-4" (selected string)
```

### With Descriptions

```python
choice = pick("Send email?", [
    ("Yes, send it", "Send immediately"),
    ("Auto approve", "Skip approval for this recipient"),
    ("No", "Cancel"),
])
```

### With "Other" Option

```python
choice = pick("Continue?", ["Yes", "No"], other=True)
# Adds "Other..." option for custom text input
```

## Keyboard Controls

| Key | Action |
|-----|--------|
| ↑/↓ | Navigate |
| 1-9 | Jump to option |
| Enter | Confirm |
| Esc | Cancel |

## API

```python
pick(
    title: str,           # Question to display
    options: list,        # Strings or (label, description) tuples
    other: bool = False,  # Add "Other..." option
    console: Console = None
) -> str                  # Returns selected label
```

## Example Output

```
Pick a color

  ❯ 1  Red
    2  Green
    3  Blue

↑↓ navigate  1-9 jump  Enter select
```
