"""
Purpose: Block bash file creation and soft-remind for file reading
LLM-Note:
  Dependencies: imports from [core/events.py] | imported by [useful_plugins/__init__.py]
  Data flow: before_each_tool fires → block file creation (ValueError) or flag file reading →
             after_each_tool fires → append soft reminder to tool result for file reading
  State/Effects: sets session['_prefer_read_file_reminder'] flag for soft reminders
  Integration: exposes prefer_write_tool plugin list
  Errors: raises ValueError only for bash file creation

Prefer Write Tool Plugin - Block bash file creation, soft-remind for file reading.

AI models often use bash commands for file operations:
- Creating: `cat <<EOF > file.py`, `echo > file.py` → BLOCKED
- Reading: `cat file.txt`, `head file.txt`, `tail file.txt` → SOFT REMINDER

File creation is blocked because it bypasses tool UI/diffs/approval flow.
File reading is allowed but a system reminder suggests using read_file tool instead.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import prefer_write_tool

    agent = Agent("assistant", tools=[bash, read_file, write], plugins=[prefer_write_tool])
"""

import re
from typing import TYPE_CHECKING

from ..core.events import before_each_tool, after_each_tool

if TYPE_CHECKING:
    from ..core.agent import Agent


# Patterns that indicate bash is being used to create/write files (hard blocked)
FILE_CREATION_PATTERNS = [
    re.compile(r"cat\s+<<"),              # cat <<EOF, cat <<'EOF', cat << 'EOF'
    re.compile(r">\s*\S+\.\w+\s*<<"),     # > file.py <<EOF
    re.compile(r"echo\s+.*[^2]>\s*\S+"),  # echo "..." > file (but not 2>)
    re.compile(r"printf\s+.*[^2]>\s*\S+"),# printf "..." > file (but not 2>)
    re.compile(r"tee\s+\S+"),             # tee file.py
    re.compile(r"(?<!\d)>\s*[~\.]"),      # > ./file, > ~/file (not 2>/dev/null)
    re.compile(r"(?<!\d)>>\s*[~\.]"),     # >> ./file, >> ~/file
]

# Patterns that indicate bash is being used to read files (standalone, not in pipelines)
# These trigger a soft reminder, not a hard block
FILE_READING_PATTERNS = [
    re.compile(r"^\s*cat\s+\S+\s*$"),           # cat file.txt (standalone, no pipe)
    re.compile(r"[;&]\s*cat\s+\S+\s*$"),        # ... && cat file.txt (standalone at end)
    re.compile(r"^\s*head\s+\S+"),              # head file.txt
    re.compile(r"[;&|]\s*head\s+\S+"),          # ... && head file.txt
    re.compile(r"^\s*tail\s+\S+"),              # tail file.txt
    re.compile(r"[;&|]\s*tail\s+\S+"),          # ... && tail file.txt
    re.compile(r"^\s*less\s+\S+"),              # less file.txt
    re.compile(r"^\s*more\s+\S+"),              # more file.txt
]


def _is_file_creation_command(command: str) -> bool:
    """Check if bash command is trying to create/write a file."""
    for pattern in FILE_CREATION_PATTERNS:
        if pattern.search(command):
            return True
    return False


def _is_file_reading_command(command: str) -> bool:
    """Check if bash command is trying to read a file."""
    for pattern in FILE_READING_PATTERNS:
        if pattern.search(command):
            return True
    return False


@before_each_tool
def block_bash_file_creation(agent: 'Agent') -> None:
    """Block bash file creation. Flag file reading for soft reminder."""
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    tool_name = pending['name'].lower()
    if tool_name not in ('bash', 'shell', 'run', 'run_in_dir'):
        return

    command = pending['arguments'].get('command', '')

    # File creation → hard block (raises ValueError)
    if _is_file_creation_command(command):
        if hasattr(agent, 'logger') and agent.logger:
            agent.logger.print("[yellow]⚠ Blocked bash file creation. Use Write tool instead.[/yellow]")

        if agent.io:
            agent.io.send({
                'type': 'tool_blocked',
                'tool': tool_name,
                'reason': 'file_creation',
                'message': 'Use Write tool instead of bash for creating files',
                'command': command,
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

    # Check for file reading — soft flag, don't block
    if _is_file_reading_command(command):
        agent.current_session['_prefer_read_file_reminder'] = True
        if hasattr(agent, 'logger') and agent.logger:
            agent.logger.print("[yellow]⚠ Consider using read_file tool instead of bash for reading files.[/yellow]")


@after_each_tool
def remind_read_file(agent: 'Agent') -> None:
    """Append soft system reminder to tool result when bash was used to read files."""
    if not agent.current_session.pop('_prefer_read_file_reminder', False):
        return

    messages = agent.current_session.get('messages', [])
    for msg in reversed(messages):
        if msg.get('role') == 'tool':
            msg['content'] = msg.get('content', '') + (
                "\n\n<system-reminder>"
                "You used bash to read a file. Consider using the read_file tool instead:\n"
                "  read_file(file_path=\"/path/to/file.txt\")\n\n"
                "Why: read_file provides line numbers, proper formatting, and better control."
                "</system-reminder>"
            )
            break


prefer_write_tool = [block_bash_file_creation, remind_read_file]
