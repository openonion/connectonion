"""
Purpose: Simple write file tool (for creating new files)
LLM-Note:
  Dependencies: imports from [pathlib] | imported by [file_tools/__init__]
  Data flow: write(path, content) -> creates/overwrites file directly
  State/Effects: writes file to filesystem
  Integration: exposes write(path, content) function | used as agent tool

Note: This is for creating NEW files. For modifying existing files,
use edit() or multi_edit() which provide diff preview and validation.
"""

from pathlib import Path


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
        return f"Error: File '{path}' already exists. Use edit() or multi_edit() to modify existing files, not write()"

    try:
        # Create parent directories if they don't exist
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(content, encoding="utf-8")

        return f"Successfully wrote {len(content)} bytes to '{path}'"

    except PermissionError:
        return f"Error: Permission denied writing to '{path}'"
    except OSError as e:
        return f"Error: Failed to write '{path}': {e}"
