# keys

Low-level keyboard input primitives.

## Quick Start

```python
from connectonion.tui import getch, read_key

# Read single character
ch = getch()  # Blocks until keypress

# Read key with arrow handling
key = read_key()  # Returns 'up', 'down', etc.
```

## getch

Read single character without waiting for Enter.

```python
from connectonion.tui import getch

ch = getch()
# Returns: 'a', '1', '\n', etc.
```

Works on both Unix (termios) and Windows (msvcrt).

## read_key

Read key with arrow/escape sequence handling.

```python
from connectonion.tui import read_key

key = read_key()
```

### Return Values

| Input | Returns |
|-------|---------|
| Arrow Up | `'up'` |
| Arrow Down | `'down'` |
| Arrow Left | `'left'` |
| Arrow Right | `'right'` |
| Escape | `'esc'` |
| Enter | `'\n'` or `'\r'` |
| Regular char | The character |

## Example: Navigation Loop

```python
from connectonion.tui import read_key

selected = 0
options = ["Option A", "Option B", "Option C"]

while True:
    key = read_key()

    if key == 'up':
        selected = max(0, selected - 1)
    elif key == 'down':
        selected = min(len(options) - 1, selected + 1)
    elif key == '\n':
        break  # Selected
    elif key == 'esc':
        selected = -1
        break  # Cancelled
```

## Platform Support

- **Unix/macOS**: Uses `termios` + `tty`
- **Windows**: Uses `msvcrt`
