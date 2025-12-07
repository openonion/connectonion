# Divider

Simple horizontal line separator.

## Quick Start

```python
from connectonion.tui import Divider
from rich.console import Console

console = Console()

divider = Divider()
console.print(divider.render())
```

## Output

```
────────────────────────────────────────
```

## Configuration

```python
# Custom width
divider = Divider(width=20)

# Custom character
divider = Divider(char="═")

# Custom style
divider = Divider(style="bold cyan")
```

## API

```python
Divider(
    width: int = 40,
    char: str = "─",
    style: str = "dim",
)
```

### Methods

```python
divider.render() -> Text  # Returns Rich Text object
```

## Usage Example

```python
from connectonion.tui import Divider, StatusBar
from rich.console import Console

console = Console()

console.print(Divider().render())
console.print(StatusBar([("🤖", "gpt-4", "magenta")]).render())
console.print(Divider().render())
```
