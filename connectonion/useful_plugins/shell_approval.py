"""
Purpose: Human-in-the-loop approval plugin for shell commands with safe command bypass
LLM-Note:
  Dependencies: imports from [re, typing, events.before_each_tool, tui.pick, rich.console] | imported by [useful_plugins/__init__.py] | tested by [tests/unit/test_shell_approval.py]
  Data flow: before_each_tool event → checks if tool is Shell.run → matches command against SAFE_PATTERNS (ls, cat, grep, git status, etc.) → if not safe, displays command with pick() for user approval → raises exception to cancel if rejected
  State/Effects: blocks on user input | displays Rich-formatted command preview | raises exception to cancel tool execution | no file I/O | no network
  Integration: exposes shell_approval plugin list with [approve_shell] handler | used via Agent(plugins=[shell_approval]) | works with Shell tool
  Performance: O(n) regex pattern matching | blocks on user input | instant for safe commands
  Errors: raises ToolCancelled exception on rejection | keyboard interrupts handled gracefully

Shell Approval plugin - Asks user approval for shell commands.

All shell commands require approval EXCEPT safe read-only commands
like ls, grep, cat, git status, etc.

Usage:
    from connectonion import Agent
    from connectonion.useful_plugins import shell_approval

    agent = Agent("assistant", tools=[shell], plugins=[shell_approval])
"""

import re
from typing import TYPE_CHECKING
from ..events import before_each_tool
from ..tui import pick
from rich.console import Console

if TYPE_CHECKING:
    from ..agent import Agent

_console = Console()

# Safe read-only commands that don't need approval
SAFE_PATTERNS = [
    r'^ls\b',                     # list files
    r'^ll\b',                     # list files (alias)
    r'^cat\b',                    # read file
    r'^head\b',                   # read file head
    r'^tail\b',                   # read file tail
    r'^less\b',                   # read file
    r'^more\b',                   # read file
    r'^grep\b',                   # search
    r'^rg\b',                     # ripgrep search
    r'^find\b',                   # find files
    r'^fd\b',                     # fd find
    r'^which\b',                  # find executable
    r'^whereis\b',                # find executable
    r'^type\b',                   # show type
    r'^file\b',                   # file type
    r'^stat\b',                   # file stats
    r'^wc\b',                     # word count
    r'^pwd\b',                    # print working dir
    r'^echo\b',                   # echo (read-only)
    r'^printf\b',                 # printf (read-only)
    r'^date\b',                   # date
    r'^whoami\b',                 # current user
    r'^id\b',                     # user id
    r'^env\b',                    # environment
    r'^printenv\b',               # print environment
    r'^uname\b',                  # system info
    r'^hostname\b',               # hostname
    r'^df\b',                     # disk free
    r'^du\b',                     # disk usage
    r'^free\b',                   # memory
    r'^ps\b',                     # processes
    r'^top\b',                    # top processes
    r'^htop\b',                   # htop
    r'^tree\b',                   # tree view
    r'^git\s+status\b',           # git status
    r'^git\s+log\b',              # git log
    r'^git\s+diff\b',             # git diff
    r'^git\s+show\b',             # git show
    r'^git\s+branch\b',           # git branch (list)
    r'^git\s+remote\b',           # git remote (list)
    r'^git\s+tag\b',              # git tag (list)
    r'^npm\s+list\b',             # npm list
    r'^npm\s+ls\b',               # npm ls
    r'^pip\s+list\b',             # pip list
    r'^pip\s+show\b',             # pip show
    r'^python\s+--version\b',     # python version
    r'^node\s+--version\b',       # node version
    r'^cargo\s+--version\b',      # cargo version
]


def _is_safe(command: str) -> bool:
    """Check if command is a safe read-only command."""
    cmd = command.strip()
    for pattern in SAFE_PATTERNS:
        if re.search(pattern, cmd):
            return True
    return False


def _check_approval(agent: 'Agent') -> None:
    """Check pending tool and ask for approval if not safe.

    All shell commands require approval except safe read-only commands.

    Raises:
        ValueError: If user rejects the command
    """
    pending = agent.current_session.get('pending_tool')
    if not pending:
        return

    # Only check bash/shell tools
    tool_name = pending['name']
    if tool_name not in ('bash', 'shell', 'run'):
        return

    # Get command from arguments
    args = pending['arguments']
    command = args.get('command', '')

    # Get the base command (first word)
    base_cmd = command.strip().split()[0] if command.strip() else ''

    # Skip if this command type was auto-approved earlier
    approved_cmds = agent.current_session.get('shell_approved_cmds', set())
    if base_cmd in approved_cmds:
        return

    # Skip approval for safe read-only commands
    if _is_safe(command):
        return

    # Show command in a visual box
    from rich.panel import Panel
    from rich.syntax import Syntax

    _console.print()
    syntax = Syntax(command, "bash", theme="monokai", word_wrap=True)
    _console.print(Panel(syntax, title="[yellow]Shell Command[/yellow]", border_style="yellow"))

    # Use pick for visual arrow-key selection
    choice = pick("Execute this command?", [
        "Yes, execute",
        f"Auto approve '{base_cmd}' in this session",
        "No, tell agent what I want"
    ], console=_console)

    if choice == "Yes, execute":
        return  # Execute the command
    elif choice.startswith("Auto approve"):
        # Add this command type to approved set
        if 'shell_approved_cmds' not in agent.current_session:
            agent.current_session['shell_approved_cmds'] = set()
        agent.current_session['shell_approved_cmds'].add(base_cmd)
        return  # Execute the command
    else:
        # User wants to provide feedback
        feedback = input("What do you want the agent to do instead? ")
        raise ValueError(f"User feedback: {feedback}")


# Plugin is an event list
shell_approval = [before_each_tool(_check_approval)]