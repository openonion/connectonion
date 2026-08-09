"""
LLM-Note: co_ai tools package - Claude Code-style tools for AI coding agents

This package provides a comprehensive toolkit for AI agents to interact with code:
- File operations (read, edit, write)
- Search capabilities (glob, grep)
- Task spawning and background process management
- User interaction and documentation loading
- Codex delegation with mode-owned permissions

Key exports:
- File tools: FileTools (read_file, edit, multi_edit, write, glob, grep)
- Task tools: task, run_background, task_output, kill_task
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

# ask_user from useful_tools (single source of truth)
from connectonion.useful_tools import ask_user

# Coding-agent delegation (CLI-specific policy wrapper)
from connectonion.cli.co_ai.tools.claude_code import claude_code

# Interaction tools (CLI-specific)
from connectonion.cli.co_ai.tools.load_guide import load_guide
from connectonion.cli.co_ai.tools.codex import codex

__all__ = [
    # File tools (Claude Code-style)
    "FileTools",
    # Task tools
    "task",
    "run_background",
    "task_output",
    "kill_task",
    # Interaction tools
    "ask_user",
    "claude_code",
    "load_guide",
    "codex",
    # Utility classes
    "TodoList",
]
