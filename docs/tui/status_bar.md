# StatusBar

Powerline-style status bar with colored segments.

## Quick Start

```python
from connectonion.tui import StatusBar
from rich.console import Console

console = Console()

status = StatusBar([
    ("🤖", "co/gemini-3.7-flash", "magenta"),
    ("📊", "50%", "green"),
    ("", "main", "blue"),
])
console.print(status.render())
```

## Segments

### Text Segments

```python
# (icon, text, color)
segments = [
    ("🤖", "gpt-4", "magenta"),
    ("💰", "$0.02", "yellow"),
    ("", "main", "blue"),
]
```

### Progress Segments

```python
from connectonion.tui import StatusBar, ProgressSegment

status = StatusBar([
    ("🤖", "gpt-4", "magenta"),
    ProgressSegment(percent=78, bg_color="green"),
])
# Output: 🤖 gpt-4  ████████░░ 78%
```

## ProgressSegment

```python
ProgressSegment(
    percent: float,        # 0-100, how much used
    bg_color: str = "green",
    width: int = 10,
    show_percent: bool = True,
)
```

## Styles

- Uses powerline arrows for segment transitions
- Falls back to unicode on terminals without powerline fonts
- Works on both light and dark terminals

## Example Output

```
🤖 co/gemini-3.7-flash  📊 50%   main
```
