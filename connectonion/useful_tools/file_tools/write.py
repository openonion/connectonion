"""
Purpose: Simple write file tool (for creating new files)
LLM-Note:
  Dependencies: imports from [pathlib] | imported by [file_tools/__init__]
  Data flow: write(path, content) -> creates file -> reads it back -> reports resolved path, size, mtime (ToolFailure if the bytes differ)
  State/Effects: writes file to filesystem
  Integration: exposes write(path, content) function | used as agent tool

Note: This is for creating NEW files. For modifying existing files,
use edit() or multi_edit() which provide diff preview and validation.
"""

import os
from datetime import datetime
from pathlib import Path

from ...core.tool_result import ToolFailure


def confirm_written(file_path: Path, content: str):
    """Read the file back and report what is actually on disk (#1338).

    The success message is the agent's only feedback: "✓" means it moves on.
    Three unattended runs once reported a write while the file kept its old
    mtime, and the log could not say where the bytes went. So a write is only
    a success once the bytes on disk are the bytes asked for, and the message
    carries the resolved path, size and mtime as its own proof.

    Text mode writes each newline as os.linesep, so that is what we expect
    to find (CRLF on Windows, unchanged elsewhere).
    """
    resolved = file_path.resolve()
    expected = content.replace("\n", os.linesep).encode("utf-8")
    try:
        on_disk = resolved.read_bytes()
    except FileNotFoundError:
        return ToolFailure(
            f"Error: wrote to '{resolved}' but no file is there afterwards. "
            "Treat this write as failed."
        )
    except OSError as e:
        return ToolFailure(
            f"Error: wrote to '{resolved}' but cannot read it back ({e}); "
            "the file was NOT verified"
        )
    if on_disk != expected:
        return ToolFailure(
            f"Error: wrote to '{resolved}' but the file on disk does not match: "
            f"expected {len(expected)} bytes, found {len(on_disk)}. "
            "Treat this write as failed."
        )
    mtime = datetime.fromtimestamp(resolved.stat().st_mtime).isoformat(timespec="seconds")
    return f"{len(expected)} bytes to '{resolved}' (verified on disk, mtime {mtime})"


def write(path: str, content: str) -> str:
    """
    Write content to a file (full overwrite).

    Primarily for creating new files. For modifying existing files,
    use edit() or multi_edit() which show diffs and validate changes.

    Args:
        path: File path to write to
        content: Complete file content

    Returns:
        Success message or error description

    Examples:
        write("new_file.py", "print('hello')")
        write("config.json", '{"debug": true}')
    """
    file_path = Path(path)

    # Check if file already exists - should use edit() instead
    if file_path.exists():
        return ToolFailure(
            f"Error: File '{path}' already exists. Use edit() or multi_edit() "
            "to modify existing files, not write()"
        )

    try:
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(content, encoding="utf-8")

        confirmed = confirm_written(file_path, content)
        if isinstance(confirmed, ToolFailure):
            return confirmed
        return f"Successfully wrote {confirmed}"

    except PermissionError:
        return ToolFailure(f"Error: Permission denied writing to '{path}'")
    except OSError as e:
        return ToolFailure(f"Error: Failed to write '{path}': {e}")
