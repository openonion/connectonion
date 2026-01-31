# Footer

Simple footer with tips/hints display.

## Quick Start

```python
from connectonion.tui import Footer
from rich.console import Console

console = Console()

footer = Footer(["? help", "/ commands", "@ contacts"])
console.print(footer.render())
```

## Output

```
? help  / commands  @ contacts
```

## API

```python
Footer(tips: list[str])
```

### Methods

```python
footer.render() -> Text  # Returns Rich Text object
```

## Usage with Input

```python
from connectonion.tui import Input, Footer

# Footer tips shown below input
text = Input(
    hints=["? help", "/ commands", "Enter submit"]
).run()
```
