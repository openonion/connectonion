# prefer_write_tool

Block bash file creation, soft-remind for file reading.

## Problem

AI models often use bash commands for file operations:

**File Creation:**
```bash
cat <<EOF > /tmp/my_script.py
import os
print("hello")
EOF
```

**File Reading:**
```bash
cat config.json
head -n 10 README.md
```

File creation via bash bypasses proper tool UI/diffs/approval flow, has escaping issues, and is harder to review.

File reading via bash works but misses line numbers, formatting, and control that `read_file` provides.

## Solution

This plugin uses two strategies:

- **File creation** → **hard block** — raises `ValueError`, agent must use `Write` or `Edit` tool instead
- **File reading** → **soft reminder** — command runs normally, but a `<system-reminder>` is appended to the tool result suggesting `read_file`

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import prefer_write_tool

agent = Agent(
    "assistant",
    tools=[bash, read_file, write, edit],
    plugins=[prefer_write_tool]
)
```

## Detected Patterns

**File Creation (hard blocked):**
- `cat <<EOF > file.py` - heredoc redirection
- `echo "..." > file.py` - output redirection
- `printf "..." > file.py` - printf redirection
- `cmd > ./file` - output redirection to path
- `cmd >> ./file` - append redirection to path
- `tee file.py` - tee command

**File Reading (soft reminder):**
- `cat file.txt` - standalone cat (not piped)
- `head file.txt` - read first lines
- `tail file.log` - read last lines
- `less file.txt` - page through file
- `more file.txt` - page through file

Note: `cat file | grep pattern` (piped cat) is **not** detected — piping is legitimate bash usage.

## What Happens

**For file creation (blocked):**
```
Bash file creation blocked.

<system-reminder>
You tried to create a file using bash. This is blocked.

Use the Write tool instead:
  Write(file_path="/path/to/file.py", content="...")

For editing existing files:
  Edit(file_path="/path/to/file.py", old_string="...", new_string="...")
</system-reminder>
```

**For file reading (soft reminder appended to result):**
```
[actual command output here]

<system-reminder>
You used bash to read a file. Consider using the read_file tool instead:
  read_file(file_path="/path/to/file.txt")

Why: read_file provides line numbers, proper formatting, and better control.
</system-reminder>
```

The command still runs — the reminder just nudges the agent toward better tools.

## How It Works

The plugin exports two event handlers:

1. `block_bash_file_creation` (`before_each_tool`) — detects file creation patterns and raises `ValueError` to block execution. For file reading, sets a session flag instead.
2. `remind_read_file` (`after_each_tool`) — if the flag is set, appends a system reminder to the tool result message.

## Combining with tool_approval

You can use both plugins together:

```python
from connectonion.useful_plugins import tool_approval, prefer_write_tool

agent = Agent(
    "assistant",
    tools=[bash, read_file, write, edit],
    plugins=[prefer_write_tool, tool_approval]  # prefer_write_tool first
)
```

Order matters - `prefer_write_tool` should come first to block file creation before `tool_approval` prompts for approval.
