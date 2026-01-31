# providers

Data providers for autocomplete in Input and CommandPalette.

## Quick Start

```python
from connectonion.tui import Input, FileProvider, StaticProvider

# File autocomplete
text = Input(triggers={"@": FileProvider()}).run()

# Command autocomplete
commands = StaticProvider([
    ("/today", "/today", "Daily briefing"),
    ("/inbox", "/inbox", "Show emails"),
])
text = Input(triggers={"/": commands}).run()
```

## StaticProvider

Provider for static list of items.

```python
from connectonion.tui import StaticProvider

# Simple (display, value)
provider = StaticProvider([
    ("/today", "/today"),
    ("/inbox", "/inbox"),
])

# With descriptions
provider = StaticProvider([
    ("/today", "/today", "Daily email briefing"),
    ("/inbox", "/inbox", "Show recent emails"),
])

# With icons
provider = StaticProvider([
    ("/today", "/today", "Daily briefing", "📅"),
    ("/inbox", "/inbox", "Show emails", "📥"),
])
```

## FileProvider

Provider for filesystem autocomplete.

```python
from connectonion.tui import FileProvider

# Default: current directory
provider = FileProvider()

# Custom root
provider = FileProvider(root="src/")

# Results include:
# - Folders with 📁 icon
# - Files with type-specific icons
# - Fuzzy matched against query
```

## Custom Provider

Implement the Provider protocol:

```python
from connectonion.tui import DropdownItem

class MyProvider:
    def search(self, query: str) -> list[DropdownItem]:
        # Return matching items
        return [
            DropdownItem(display="Result", value="result"),
        ]
```

## Provider Protocol

```python
class Provider(Protocol):
    def search(self, query: str) -> list[DropdownItem]:
        ...
```

Returns list of `DropdownItem` or tuples `(display, value, score, positions)`.
