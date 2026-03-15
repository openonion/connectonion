"""
LLM-Note: co_ai tools package - Claude Code-style tools for AI coding agents

This package provides a comprehensive toolkit for AI agents to interact with code:
- File operations (read, edit, write)
- Search capabilities (glob, grep)
- Task spawning and background process management
- Planning mode for complex implementations
- User interaction and documentation loading

Key exports:
- File tools: FileTools (read_file, edit, multi_edit, write, glob, grep)
- Task tools: task, run_background, task_output, kill_task
- Planning tools: enter_plan_mode, exit_plan_and_implement, write_plan
- Interaction tools: ask_user, load_guide
- Utilities: TodoList

Note: All file tools re-exported from connectonion.useful_tools.file_tools (single source of truth).
"""

"""
Coding tools for the AI agent (Claude Code-style).

File Tools (via FileTools class):
    - FileTools.read_file: Read file with line numbers
    - FileTools.edit: Precise string replacement (str_replace)
    - FileTools.multi_edit: Multiple atomic string replacements
    - FileTools.write: Create new files (errors if file exists)
    - FileTools.glob: Find files by pattern
    - FileTools.grep: Search file contents

Task Tools:
    - task: Spawn sub-agent for complex tasks
    - run_background: Run command in background
    - task_output: Get background task output
    - kill_task: Stop background task

Planning Tools:
    - enter_plan_mode: Switch to planning mode
    - exit_plan_and_implement: Exit planning mode
    - write_plan: Write plan content

Interaction Tools:
    - ask_user: Ask user a question via io
    - load_guide: Load documentation/guide

Utility Classes:
    - TodoList: Task list management

Note: All file tools are re-exported from connectonion.useful_tools.file_tools (single source of truth).
"""

# File tools (Claude Code-style) - import from useful_tools/file_tools (single source of truth)
from connectonion.useful_tools.file_tools import FileTools

# TodoList from useful_tools
from connectonion.useful_tools import TodoList

# Task tools (CLI-specific)
from connectonion.cli.co_ai.tools.task import task
from connectonion.cli.co_ai.tools.background import run_background, task_output, kill_task

# Planning tools (CLI-specific)
from connectonion.cli.co_ai.tools.plan_mode import enter_plan_mode, exit_plan_and_implement, write_plan

# Interaction tools (CLI-specific)
from connectonion.cli.co_ai.tools.ask_user import ask_user
from connectonion.cli.co_ai.tools.load_guide import load_guide

__all__ = [
    # File tools (Claude Code-style)
    "FileTools",
    # Task tools
    "task",
    "run_background",
    "task_output",
    "kill_task",
    # Planning tools
    "enter_plan_mode",
    "exit_plan_and_implement",
    "write_plan",
    # Interaction tools
    "ask_user",
    "load_guide",
    # Utility classes
    "TodoList",
]
