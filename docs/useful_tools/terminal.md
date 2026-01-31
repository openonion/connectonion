# Terminal

Interactive terminal utilities: selection menus, file browser, and input with autocomplete.

## Usage

**Option 1: Import directly**

```python
from connectonion import pick, yes_no, browse_files, input_with_at
```

**Option 2: Copy and customize**

```bash
co copy terminal
```

```python
from tools.terminal import pick, yes_no, browse_files, input_with_at  # Your local copy
```

## Quick Start

```python
from connectonion import pick, yes_no, browse_files, input_with_at

# Selection menu
choice = pick("Pick a color", ["Red", "Green", "Blue"])

# Yes/No confirmation
ok = yes_no("Are you sure?")

# File browser
path = browse_files()

# Input with @ file autocomplete
cmd = input_with_at("> ")
```

## pick()

Single-select menu with keyboard navigation.

```python
# List options (press 1, 2, 3 or arrow keys)
choice = pick("Apply this command?", [
    "Yes, apply",
    "Yes for same command",
    "No, tell agent how"
])

# Dict options (returns key)
choice = pick("Continue?", {
    "y": "Yes, continue",
    "n": "No, cancel",
})
```

## yes_no()

Simple binary confirmation.

```python
ok = yes_no("Delete this file?")
# Press y → True, n → False
```

## browse_files()

Navigate and select files.

```python
path = browse_files()
# Arrow keys to navigate
# Enter on folder to open
# Enter on file to select
# Returns: "src/agent.py"
```

## input_with_at()

Text input with @ file autocomplete.

```python
cmd = input_with_at("> ")
# User types: "edit @"
# File browser opens automatically
# Returns: "edit src/agent.py"
```

## Keyboard Controls

| Key | Action |
|-----|--------|
| ↑/↓ | Navigate options |
| 1-9 | Quick select by number |
| Enter | Confirm selection |
| Esc | Cancel |
| @ | Trigger file autocomplete |

## Customizing

Need to modify terminal utilities? Copy the source to your project:

```bash
co copy terminal
```

Then import from your local copy:

```python
# from connectonion import pick, yes_no  # Before
from tools.terminal import pick, yes_no   # After - customize freely!
```
