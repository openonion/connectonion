"""
LLM-Note: co_ai tools package - Claude Code-style tools for AI coding agents

This package provides a comprehensive toolkit for AI agents to interact with code:
- File operations (read, edit, write)
- Search capabilities (glob, grep)
- Task spawning and background process management
- User interaction and documentation loading
- Codex delegation is installed by `CodexPlugin`, not this COAI tool package

Key exports:
- File tools: FileTools (read_file, edit, multi_edit, write, glob, grep)
- Task tools: task, run_background, task_output, kill_task
- Interaction tools: ask_user, load_guide
- Utilities: TodoList

Note: All file tools re-exported from connectonion.useful_tools.file_tools (single source of truth).
"""

from connectonion.cli.co_ai.tools.background import (
    kill_task,
    run_background,
    task_output,
)
from connectonion.cli.co_ai.tools.claude_code import claude_code
from connectonion.cli.co_ai.tools.load_guide import load_guide
from connectonion.cli.co_ai.tools.task import task
from connectonion.useful_tools import TodoList, ask_user
from connectonion.useful_tools.file_tools import FileTools

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
    # Utility classes
    "TodoList",
]
