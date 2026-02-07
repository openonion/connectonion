# prefer_write_tool

Block bash file creation, remind agent to use Write tool instead.

## Problem

AI models often create files using bash commands:

```bash
cat <<EOF > /tmp/my_script.py
import os
print("hello")
EOF
```

This is an anti-pattern because:
- Bypasses file editing UI/diffs
- Escaping issues with special characters
- Harder to review and track changes

## Solution

This plugin detects bash file creation patterns **before execution** and rejects them with a system reminder telling the agent to use Write tool.

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import prefer_write_tool

agent = Agent(
    "assistant",
    tools=[bash, write, edit],
    plugins=[prefer_write_tool]
)
```

## Detected Patterns

- `cat <<EOF > file.py`
- `cat <<'EOF' > file.py`
- `echo "..." > file.py`
- `printf "..." > file.py`
- `tee file.py`

## What Happens

When detected, the tool is rejected and the agent receives:

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

The agent will then use the proper Write/Edit tools.

## Combining with tool_approval

You can use both plugins together:

```python
from connectonion.useful_plugins import tool_approval, prefer_write_tool

agent = Agent(
    "assistant",
    tools=[bash, write, edit],
    plugins=[prefer_write_tool, tool_approval]  # prefer_write_tool first
)
```

Order matters - `prefer_write_tool` should come first to block file creation before `tool_approval` prompts for approval.
