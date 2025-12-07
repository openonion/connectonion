# Dropdown

Selection list component for autocomplete menus.

## Quick Start

```python
from connectonion.tui import Dropdown, DropdownItem

# Create items
items = [
    DropdownItem(display="/today", value="/today", description="Daily briefing"),
    DropdownItem(display="/inbox", value="/inbox", description="Show emails"),
]

# Create dropdown
dropdown = Dropdown(items, max_visible=5, style="modern")
```

## DropdownItem

Structured item with rich metadata.

```python
from connectonion.tui import DropdownItem

# Simple item
item = DropdownItem(display="/today", value="/today")

# With description
item = DropdownItem(
    display="/today",
    value="/today",
    description="Daily email briefing",
    icon="📅"
)

# Contact style
item = DropdownItem(
    display="Davis Baer",
    value="davis@oneupapp.io",
    description="davis@oneupapp.io",
    subtitle="OneUp · founder",
    icon="👤"
)
```

## API

### DropdownItem

```python
DropdownItem(
    display: str,          # Main text to show
    value: Any,            # Value returned when selected
    score: int = 0,        # Match score for sorting
    positions: list = [],  # Matched char positions (for highlighting)
    description: str = "", # Secondary text
    subtitle: str = "",    # Third line
    icon: str = "",        # Left icon (emoji)
    style: str = "",       # Rich style
)
```

### Dropdown

```python
Dropdown(
    items: list[DropdownItem],
    max_visible: int = 8,
    selected: int = 0,
    style: str = "modern",
)
```

## File Icons

Built-in icons for common file types:
- 📁 folder
- 📄 file (default)
- 🐍 .py
- 📜 .js, .ts
- ⚙️ .json, .yaml
