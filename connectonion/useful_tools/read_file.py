"""
Purpose: Read file tool with line numbers
LLM-Note:
  Dependencies: imports from [pathlib, typing] | imported by [useful_tools/__init__]
  Data flow: Agent calls read_file(path) -> reads file -> returns content with line numbers
  State/Effects: reads file from filesystem
  Integration: exposes read_file(path, offset, limit) function | used as agent tool

Usage:
    read_file("app.py")                    # Read entire file
    read_file("large.log", offset=100)     # Start from line 100
    read_file("data.csv", limit=50)        # First 50 lines
"""

from pathlib import Path
from typing import Optional


def read_file(
    path: str,
    offset: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """
    Read and return the contents of a file with line numbers.

    Args:
        path: Path to the file to read
        offset: Line number to start from (1-indexed, default: 1)
        limit: Number of lines to read (default: 2000)

    Returns:
        File contents with line numbers

    Examples:
        read_file("app.py")                    # Read entire file
        read_file("large.log", offset=100)     # Start from line 100
        read_file("data.csv", limit=50)        # First 50 lines
    """
    file_path = Path(path)

    if not file_path.exists():
        return f"Error: File '{path}' does not exist"

    if not file_path.is_file():
        return f"Error: '{path}' is not a file"

    content = file_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    total_lines = len(lines)

    # Apply offset and limit
    start = (offset - 1) if offset and offset > 0 else 0
    end = (start + limit) if limit else len(lines)

    selected_lines = lines[start:end]

    # Format with line numbers
    result_lines = []
    for i, line in enumerate(selected_lines, start=start + 1):
        # Truncate very long lines
        if len(line) > 500:
            line = line[:500] + "..."
        result_lines.append(f"{i:>6}\t{line}")

    result = "\n".join(result_lines)

    # Add info about truncation
    if end < total_lines:
        result += f"\n\n... ({total_lines - end} more lines)"

    return result
