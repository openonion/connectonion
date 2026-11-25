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

import codecs
from pathlib import Path
from typing import Optional

from ...core.tool_result import ToolFailure

# A byte-order mark states the file's encoding. Decoding everything as plain
# UTF-8 leaves the mark as a literal U+FEFF on the first line and turns a
# UTF-16 file into NUL-separated mojibake. UTF-32-LE is checked before
# UTF-16-LE because its mark (FF FE 00 00) starts with the UTF-16 one (FF FE).
_BOM_ENCODINGS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


def _decode_text(raw: bytes) -> str:
    """Decode file bytes by their byte-order mark, falling back to UTF-8.

    Undecodable bytes become U+FFFD instead of raising: this is a reader, and
    half a line is still useful to the agent.
    """
    for bom, encoding in _BOM_ENCODINGS:
        if raw.startswith(bom):
            return raw.decode(encoding, errors="replace")
    return raw.decode("utf-8", errors="replace")


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
        return ToolFailure(f"Error: File '{path}' does not exist")

    if not file_path.is_file():
        return ToolFailure(f"Error: '{path}' is not a file")

    content = _decode_text(file_path.read_bytes())
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
