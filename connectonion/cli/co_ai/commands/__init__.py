"""
LLM-Note: Built-in slash commands for co ai interactive CLI.

This module exports all built-in commands that users can invoke with
slash syntax (e.g., /help, /cost, /sessions) in the co ai interface.

Available commands:
- /init: Initialize project context
- /help: Show available commands
- /cost: Show token costs for current session
- /compact: Trigger context compaction
- /tasks: Show todo list
- /export: Export session to markdown/YAML
- /sessions: List saved sessions
- /new: Start new session
- /resume: Resume saved session
- /undo: Undo last edit
- /redo: Redo undone edit

Architecture:
- BUILTIN_COMMANDS dict maps command names to functions
- set_agent_for_commands() injects agent reference for stateful commands
- Each command in separate file (init.py, help.py, cost.py, etc.)
- Commands receive user input and agent context

Used by:
- slash_command tool in tools/slash_command.py
- Interactive co ai CLI
"""

from connectonion.cli.co_ai.commands.init import cmd_init
from connectonion.cli.co_ai.commands.help import cmd_help
from connectonion.cli.co_ai.commands.cost import cmd_cost, set_agent as set_cost_agent
from connectonion.cli.co_ai.commands.compact import cmd_compact, set_agent as set_compact_agent
from connectonion.cli.co_ai.commands.tasks import cmd_tasks
from connectonion.cli.co_ai.commands.export import cmd_export, set_agent as set_export_agent
from connectonion.cli.co_ai.commands.sessions import cmd_sessions, cmd_new, cmd_resume, set_agent as set_sessions_agent
from connectonion.cli.co_ai.commands.undo import cmd_undo, cmd_redo, set_agent as set_undo_agent

BUILTIN_COMMANDS = {
    "init": cmd_init,
    "help": cmd_help,
    "cost": cmd_cost,
    "compact": cmd_compact,
    "tasks": cmd_tasks,
    "export": cmd_export,
    "sessions": cmd_sessions,
    "new": cmd_new,
    "resume": cmd_resume,
    "undo": cmd_undo,
    "redo": cmd_redo,
}


def set_agent_for_commands(agent):
    """Set agent reference for commands that need it."""
    set_cost_agent(agent)
    set_compact_agent(agent)
    set_export_agent(agent)
    set_sessions_agent(agent)
    set_undo_agent(agent)


__all__ = [
    "BUILTIN_COMMANDS",
    "cmd_init",
    "cmd_help",
    "cmd_cost",
    "cmd_compact",
    "cmd_tasks",
    "cmd_export",
    "set_agent_for_commands",
]
