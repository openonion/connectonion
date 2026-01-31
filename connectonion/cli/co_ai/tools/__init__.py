"""
Coding tools for the AI agent (Claude Code-style).

File Tools:
    - read_file: Read file with line numbers
    - edit: Precise string replacement (str_replace)
    - multi_edit: Multiple atomic string replacements
    - write: Full file overwrite with approval
    - Write: Class-based write with mode control

Search Tools:
    - glob: Find files by pattern
    - grep: Search file contents

Task Tools:
    - task: Spawn sub-agent for complex tasks
    - run_background: Run command in background
    - task_output: Get background task output
    - kill_task: Stop background task

Planning Tools:
    - enter_plan_mode: Switch to planning mode
    - exit_plan_mode: Exit planning mode
    - write_plan: Write plan content

Interaction Tools:
    - ask_user: Ask user a question via io
    - load_guide: Load documentation/guide

Utility Classes:
    - DiffWriter: Low-level file writer with diff preview
    - TodoList: Task list management

Note: File tools are re-exported from connectonion.useful_tools for consistency.
"""

# File tools (Claude Code-style) - re-export from useful_tools
from connectonion.useful_tools import (
    read_file,
    edit,
    multi_edit,
    glob,
    grep,
    write,
    FileWriter,
    DiffWriter,
    MODE_NORMAL,
    MODE_AUTO,
    MODE_PLAN,
    TodoList,
)

# Task tools (CLI-specific)
from connectonion.cli.co_ai.tools.task import task
from connectonion.cli.co_ai.tools.background import run_background, task_output, kill_task

# Planning tools (CLI-specific)
from connectonion.cli.co_ai.tools.plan_mode import enter_plan_mode, exit_plan_mode, write_plan

# Interaction tools (CLI-specific)
from connectonion.cli.co_ai.tools.ask_user import ask_user
from connectonion.cli.co_ai.tools.load_guide import load_guide

__all__ = [
    # File tools (Claude Code-style)
    "read_file",
    "edit",
    "multi_edit",
    "write",
    "FileWriter",
    "DiffWriter",
    "MODE_NORMAL",
    "MODE_AUTO",
    "MODE_PLAN",
    # Search tools
    "glob",
    "grep",
    # Task tools
    "task",
    "run_background",
    "task_output",
    "kill_task",
    # Planning tools
    "enter_plan_mode",
    "exit_plan_mode",
    "write_plan",
    # Interaction tools
    "ask_user",
    "load_guide",
    # Utility classes
    "TodoList",
]
