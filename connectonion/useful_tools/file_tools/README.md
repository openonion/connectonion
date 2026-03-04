# File Tools

Claude Code-style file operations with read-before-edit tracking and permission control.

## Quick Start

```python
from connectonion.useful_tools import FileTools

# Full access (read + write with snapshot tracking)
agent = Agent("coder", tools=[FileTools()])

# Read-only mode
agent = Agent("reader", tools=[FileTools(permission="read")])
```

## Architecture

### Simplified and Consistent Design

All file tools are now **simple, pure functions** with consistent naming:

```
file_tools/
├── read.py         → read_file()
├── edit.py         → edit()
├── multi_edit.py   → multi_edit()
├── write.py        → write()       (NEW: simplified, no DiffWriter)
├── glob.py         → glob()
├── grep.py         → grep()
└── file_tools.py   → FileTools class (wrapper with state tracking)
```

**Key Changes:**
- ✅ **Removed DiffWriter** from `write()` - now a pure function
- ✅ **Consistent naming** - all files match function names
- ✅ **write() enforces new-file-only** - returns error if file exists
- ✅ **No agent parameter** needed for write()
- ✅ **27 comprehensive tests** covering all operations

## Features

### 1. Read-Before-Edit Validation
`FileTools` tracks which files have been read and prevents edits without prior reads:

```python
ft = FileTools()

# This will fail - file not read yet
ft.edit("app.py", "old", "new")
# Error: Read 'app.py' before editing (use read_file first)

# Read first, then edit
ft.read_file("app.py")
ft.edit("app.py", "old", "new")  # ✓ Success
```

### 2. Stale Read Detection (MD5 Snapshots)
Detects external file changes between read and edit:

```python
ft = FileTools()

ft.read_file("config.json")
# ... external process changes config.json ...
ft.edit("config.json", "old", "new")
# Error: 'config.json' changed since last read - re-read it first
```

### 3. write() for NEW Files Only
`write()` now prevents overwriting existing files:

```python
ft = FileTools()

# Create new file - works
ft.write("new.py", "print('hello')")  # ✓ Success

# Try to overwrite - fails with helpful message
ft.write("new.py", "print('world')")
# Error: File 'new.py' already exists. Use edit() or multi_edit() to modify existing files
```

**Design rationale:** `write()` is for creating files. For modifications, use `edit()` which provides diff tracking and validation.

### 4. Permission Modes

**Write mode** (default) - full access:
```python
ft = FileTools(permission="write")
ft.read_file("app.py")    # ✓
ft.edit("app.py", ...)    # ✓
ft.write("new.py", ...)   # ✓
```

**Read-only mode**:
```python
ft = FileTools(permission="read")
ft.read_file("app.py")    # ✓
ft.glob("**/*.py")        # ✓
ft.grep("pattern")        # ✓
ft.edit("app.py", ...)    # ✗ Permission denied
ft.write("new.py", ...)   # ✗ Permission denied
```

## API Reference

### `read_file(path, offset=None, limit=None)`
Read file with line numbers. Automatically tracks MD5 snapshot.

**Returns:** File contents with line numbers (format: `42→code`)

### `edit(file_path, old_string, new_string, replace_all=False)`
Replace string in file. Validates read-before-edit and detects stale reads.

**Validation:**
1. File must be read first (snapshot exists)
2. File must not have changed since read (MD5 check)
3. `old_string` must be unique (or use `replace_all=True`)

### `multi_edit(file_path, edits)`
Apply multiple edits atomically. All succeed or none applied.

**Example:**
```python
multi_edit("app.py", [
    {"old_string": "foo", "new_string": "bar"},
    {"old_string": "hello", "new_string": "world", "replace_all": True}
])
```

### `write(path, content)`
Create NEW files only. Returns error if file exists.

**Behavior:**
- ✓ Creates parent directories automatically
- ✗ Fails if file already exists (suggests using `edit()`)
- ✓ Tracks snapshot after write for subsequent edits

### `glob(pattern, path=None)`
Search files by glob pattern. Returns max 100 results, ignores common directories.

**Examples:**
```python
glob("**/*.py")           # All Python files recursively
glob("src/**/*.tsx")      # All TSX files in src/
glob("*.md", "docs")      # Markdown in docs/ directory
```

### `grep(pattern, path=None, file_pattern=None, output_mode="files", context_lines=0, ignore_case=False, max_results=50)`
Search file contents with regex.

**Output modes:**
- `"files"` - Just file paths (default)
- `"content"` - Matching lines with context
- `"count"` - Match counts per file

## Implementation Details

### Snapshot Tracking (MD5)
- Hash calculated on `read_file()`
- Validated before `edit()` and `multi_edit()`
- Updated after successful edits
- More reliable than timestamps

### Why write() Enforces New-File-Only
**Old behavior (removed):** Used DiffWriter, showed diff, asked for approval
**Problem:** Over-complicated, required agent.io, didn't make sense for new files

**New behavior:** Simple create-only function
- New files → no diff to show, just create
- Existing files → error, forces agent to use `edit()` with validation

### Removed DiffWriter from write()
DiffWriter still available at `connectonion.useful_tools.DiffWriter` for web apps that need approval flow, but not forced into basic file operations.

## Backward Compatibility

Individual functions still available without FileTools wrapper:

```python
from connectonion.useful_tools import read_file, edit, write, glob, grep

agent = Agent("custom", tools=[read_file, edit, write])
# No state tracking, no read-before-edit enforcement
# write() still prevents overwriting (built into function)
```

## Usage Examples

### File editing agent with safety
```python
from connectonion import Agent
from connectonion.useful_tools import FileTools

agent = Agent(
    "code-reviewer",
    model="co/gemini-2.5-pro",
    tools=[FileTools()],
    instructions="Review and fix code. Always read files before editing."
)

agent.input("Fix typos in README.md")
```

### Read-only documentation agent
```python
agent = Agent(
    "doc-analyzer",
    tools=[FileTools(permission="read")],
    instructions="Analyze codebase structure and document findings."
)
```

### Code generation agent (creates new files)
```python
agent = Agent(
    "code-gen",
    tools=[FileTools()],
    instructions="Generate new code files. Use write() for new files, edit() for modifications."
)

agent.input("Create a new FastAPI endpoint for user registration")
```

## Testing

27 comprehensive tests covering:
- ✅ All file operations (read, edit, multi_edit, write, glob, grep)
- ✅ FileTools class (snapshots, permissions, validation)
- ✅ Edge cases (long lines, empty edits, missing files, etc.)
- ✅ Integration scenarios

Run tests:
```bash
pytest tests/unit/test_useful_tools_files.py -v
```
