"""
LLM-Note: co-ai package - AI coding agent CLI tool built with ConnectOnion.

This package implements the `co ai` command that starts an intelligent
coding assistant with file operations, planning, and background task execution.

Main export:
- create_coding_agent(): Factory function for agent with full tool suite

Package structure:
- agent.py: Agent factory with tools/plugins
- main.py: Web server entry point
- context.py: Project context loading (CLAUDE.md, git status, etc.)
- sessions.py: SQLite session persistence
- commands/: CLI commands (init, cost, export, sessions, etc.)
- tools/: Agent tools (edit, read, glob, grep, task, plan_mode, etc.)
- prompts/: System prompt templates
- skills/: User-defined skills system
- plugins/: Agent plugins (system_reminder)

Used by:
- CLI: `co ai` command in cli/main.py
- Web interface: chat.openonion.ai
"""

from connectonion.cli.co_ai.agent import create_coding_agent

__version__ = "0.1.0"
__all__ = ["create_coding_agent"]
