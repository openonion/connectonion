"""
Purpose: Write file tool with Claude Code-style approval (web mode)
LLM-Note:
  Dependencies: imports from [.diff_writer] | imported by [co_ai.tools.__init__]
  Data flow: Agent calls write(path, content) -> DiffWriter handles approval via io -> writes file
  State/Effects: writes file to filesystem | sends events via io for approval
  Integration: exposes write(path, content) function and Write class | used as agent tool

This is a wrapper around DiffWriter for simpler function-based usage.
For class-based usage with mode control, use DiffWriter directly.
"""

from pathlib import Path
from typing import Optional

from .diff_writer import DiffWriter, MODE_NORMAL, MODE_AUTO, MODE_PLAN


# Global writer instance for function-based API
_writer: Optional[DiffWriter] = None


def _get_writer() -> DiffWriter:
    """Get or create the global writer instance."""
    global _writer
    if _writer is None:
        _writer = DiffWriter(mode=MODE_AUTO)  # Default to auto for function API
    return _writer


def write(path: str, content: str) -> str:
    """
    Write content to a file (full overwrite).

    For new files or when replacing most of the content.
    Use edit() for small, targeted changes instead.

    Args:
        path: File path to write to
        content: Complete file content

    Returns:
        Success message or error description

    Examples:
        write("new_file.py", "print('hello')")
        write("config.json", '{"debug": true}')
    """
    writer = _get_writer()
    return writer.write(path, content)


class Write:
    """File writer with Claude Code-style permission modes (web mode).

    Use this class when you need mode control (normal/auto/plan).
    For simple writes, use the write() function instead.

    Usage:
        writer = Write(mode="normal")  # Prompt for every write
        writer = Write(mode="auto")    # Auto-approve all writes
        writer = Write(mode="plan")    # Read-only, preview only
    """

    def __init__(self, mode: str = MODE_NORMAL):
        """Initialize Write tool.

        Args:
            mode: Permission mode - "normal" (prompt), "auto" (auto-approve), "plan" (read-only)
        """
        self._writer = DiffWriter(mode=mode)

    @property
    def io(self):
        """IO channel for web mode."""
        return self._writer.io

    @io.setter
    def io(self, value):
        """Set IO channel."""
        self._writer.io = value

    @property
    def mode(self):
        """Current permission mode."""
        return self._writer.mode

    @mode.setter
    def mode(self, value):
        """Set permission mode."""
        self._writer.mode = value

    def write(self, path: str, content: str) -> str:
        """Write content to a file with approval.

        Args:
            path: File path to write to
            content: Complete file content

        Returns:
            Success message, rejection with feedback, or plan mode preview
        """
        return self._writer.write(path, content)

    def diff(self, path: str, content: str) -> str:
        """Show diff without writing (preview mode).

        Args:
            path: File path to compare against
            content: New content to compare

        Returns:
            Diff string in unified format
        """
        return self._writer.diff(path, content)

    def read(self, path: str) -> str:
        """Read file contents.

        Args:
            path: File path to read

        Returns:
            File contents or error message
        """
        return self._writer.read(path)
