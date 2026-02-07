"""
Purpose: Reject bash file creation and remind agent to use Write tool instead
LLM-Note:
  Dependencies: imports from [core/events.py] | imported by [useful_plugins/__init__.py]
  Data flow: before_each_tool fires → detect bash file creation → raise ValueError with system reminder
  State/Effects: none (rejects tool before execution)
  Integration: exposes prefer_write_tool plugin list
  Errors: raises ValueError when bash tries to create files

Prefer Write Tool Plugin - Block bash file creation, remind to use Write tool.

AI models often use `cat <<EOF > file.py` or `echo > file.py` to create files.
This is an anti-pattern because:
1. Bypasses file editing UI/diffs
2. Escaping issues with special characters
3. Harder to review and track

This plugin detects these patterns BEFORE execution and rejects with a reminder.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import prefer_write_tool

    agent = Agent("assistant", tools=[bash, write], plugins=[prefer_write_tool])
"""

import re
from typing import TYPE_CHECKING

from ..core.events import before_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent


# Patterns that indicate bash is being used to create/write files
FILE_CREATION_PATTERNS = [
    re.compile(r"cat\s+<<"),           # cat <<EOF, cat <<'EOF', cat << 'EOF'
    re.compile(r">\s*\S+\.\w+\s*<<"),   # > file.py <<EOF
    re.compile(r"echo\s+.*>\s*\S+"),    # echo "..." > file
    re.compile(r"printf\s+.*>\s*\S+"),  # printf "..." > file
    re.compile(r"tee\s+\S+"),           # tee file.py
]


def _is_file_creation_command(command: str) -> bool:
    """Check if bash command is trying to create/write a file."""
    for pattern in FILE_CREATION_PATTERNS:
        if pattern.search(command):
            return True
    return False


@before_each_tool
def block_bash_file_creation(agent: 'Agent') -> None:
    """Block bash commands that create files, remind to use Write tool."""
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    tool_name = pending['name'].lower()
    if tool_name not in ('bash', 'shell', 'run', 'run_in_dir'):
        return

    command = pending['arguments'].get('command', '')
    if not _is_file_creation_command(command):
        return

    # Log the block
    if hasattr(agent, 'logger') and agent.logger:
        agent.logger.print("[yellow]⚠ Blocked bash file creation. Use Write tool instead.[/yellow]")

    # Send to UI
    if agent.io:
        agent.io.send({
            'type': 'tool_blocked',
            'tool': tool_name,
            'reason': 'file_creation',
            'message': 'Use Write tool instead of bash for creating files',
        })

    raise ValueError(
        "Bash file creation blocked."
        "\n\n<system-reminder>"
        "You tried to create a file using bash (cat <<EOF, echo >, etc). This is blocked.\n\n"
        "Use the Write tool instead:\n"
        "  Write(file_path=\"/path/to/file.py\", content=\"...\")\n\n"
        "For editing existing files:\n"
        "  Edit(file_path=\"/path/to/file.py\", old_string=\"...\", new_string=\"...\")\n\n"
        "Why: Write tool shows diffs, has approval flow, handles escaping correctly.\n"
        "Do NOT retry with bash. Use Write tool now."
        "</system-reminder>"
    )


prefer_write_tool = [block_bash_file_creation]
