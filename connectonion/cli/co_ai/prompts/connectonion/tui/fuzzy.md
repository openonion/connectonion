# fuzzy

Fuzzy matching utilities for autocomplete.

## Quick Start

```python
from connectonion.tui import fuzzy_match, highlight_match

# Check if query matches text
matched, score, positions = fuzzy_match("gp", "gpt-4")
# matched: True
# score: 16 (higher = better)
# positions: [0, 1] (matched char indices)
```

## fuzzy_match

Match query against text with scoring.

```python
from connectonion.tui import fuzzy_match

matched, score, positions = fuzzy_match(query, text)
```

### Scoring

- **+1** per matched character
- **+10** consecutive character bonus
- **+5** word boundary bonus (after `/_-. `)

### Examples

```python
fuzzy_match("gp", "gpt-4")     # (True, 16, [0, 1])
fuzzy_match("g4", "gpt-4")     # (True, 7, [0, 4])
fuzzy_match("xyz", "gpt-4")    # (False, 0, [])
fuzzy_match("", "anything")    # (True, 0, [])
```

## highlight_match

Highlight matched characters in Rich Text.

```python
from connectonion.tui import highlight_match
from rich.console import Console

console = Console()

# Get match positions
matched, score, positions = fuzzy_match("gp", "gpt-4")

# Create highlighted text
text = highlight_match("gpt-4", positions)
console.print(text)  # "gp" highlighted in magenta
```

## API

```python
fuzzy_match(query: str, text: str) -> tuple[bool, int, list[int]]
# Returns: (matched, score, positions)

highlight_match(text: str, positions: list[int]) -> Text
# Returns: Rich Text with matched chars highlighted
```
