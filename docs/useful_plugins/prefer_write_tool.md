# prefer_write_tool

Block bash file operations, remind agent to use proper tools instead.

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

This is an anti-pattern because:
- Bypasses proper tool UI/diffs/approval flow
- Escaping issues with special characters
- Harder to review and track changes
- No line numbers or formatting for reading

## Solution

This plugin detects bash file operations **before execution** and rejects them with a system reminder telling the agent to use the proper tools (read_file, write, edit).

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

**File Creation (blocked):**
- `cat <<EOF > file.py` - heredoc redirection
- `echo "..." > file.py` - output redirection
- `printf "..." > file.py` - printf redirection
- `cmd > file` - any output redirection
- `cmd >> file` - append redirection
- `tee file.py` - tee command

**File Reading (blocked):**
- `cat file.txt` - read file contents
- `head file.txt` - read first lines
- `tail file.log` - read last lines
- `less file.txt` - page through file
- `more file.txt` - page through file

## What Happens

When detected, the tool is rejected and the agent receives a system reminder:

**For file creation:**
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

**For file reading:**
```
Bash file reading blocked.

<system-reminder>
You tried to read a file using bash. This is blocked.

Use the read_file tool instead:
  read_file(file_path="/path/to/file.txt")

Why: read_file provides line numbers, proper formatting, and better control.
</system-reminder>
```

The agent will then use the proper tools (read_file, write, edit).

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
