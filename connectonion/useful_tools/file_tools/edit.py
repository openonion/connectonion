"""
Purpose: Edit tool for precise string replacement (Claude Code-style)
LLM-Note:
  Dependencies: imports from [pathlib] | imported by [useful_tools/__init__]
  Data flow: Agent calls edit(file_path, old_string, new_string) -> validates -> matches verbatim first, then in the file's dominant line ending -> replaces -> writes back byte-for-byte, in the endings the matched span used
  State/Effects: reads and writes file on filesystem
  Integration: exposes edit(file_path, old_string, new_string) function | used as agent tool
  Errors: returns error if file not found | returns error if old_string not found | returns error if old_string not unique

Usage:
    edit("app.py", "def foo():", "def bar():")
    edit("config.json", '"debug": false', '"debug": true')
    edit("README.md", "v1.0", "v2.0", replace_all=True)
"""

from pathlib import Path

from ...core.tool_result import ToolFailure


def _dominant_newline(content: str) -> str:
    """The line ending most lines in ``content`` use."""
    crlf = content.count("\r\n")
    lf_only = content.count("\n") - crlf
    return "\r\n" if crlf > lf_only else "\n"


def _with_newline(text: str, newline: str) -> str:
    """Express ``text`` with ``newline``."""
    normalised = text.replace("\r\n", "\n")
    return normalised if newline == "\n" else normalised.replace("\n", "\r\n")


def edit(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    """
    Replace a string in a file with precise matching.

    More token-efficient than rewriting entire files. Use for small, targeted changes.
    The old_string must exist in the file (and be unique unless replace_all=True).

    Args:
        file_path: Path to the file to edit
        old_string: Exact string to replace (must be unique in file)
        new_string: String to replace with
        replace_all: If True, replace all occurrences; if False, old_string must be unique

    Returns:
        Success message or error description

    Examples:
        edit("app.py", "def foo():", "def bar():")
        edit("config.json", '"debug": false', '"debug": true')
        edit("README.md", "v1.0", "v2.0", replace_all=True)
    """
    path = Path(file_path)

    if not path.exists():
        return ToolFailure(f"Error: File '{file_path}' does not exist")

    if not path.is_file():
        return ToolFailure(f"Error: '{file_path}' is not a file")

    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return ToolFailure(f"Error: '{file_path}' is not UTF-8 text: {e}")

    # Line endings belong to the file, not to the platform running the edit.
    # Text-mode read+write converts a CRLF file to LF on Linux and an LF file to
    # CRLF on Windows, so changing one line rewrites the whole file in a diff.
    # Decode the bytes as they are and write back in the file's own style.
    dominant = _dominant_newline(content)

    # Try the caller's string exactly as written first. A file with mixed
    # endings -- scraped fixtures, HTTP or mail dumps -- has no single style,
    # and translating before matching would refuse edits on whichever sections
    # use the minority ending. Only when the verbatim string is not there do we
    # assume the caller wrote plain \n and express it in the file's style.
    old_in_file = old_string
    count = content.count(old_in_file)
    if count == 0:
        old_in_file = _with_newline(old_string, dominant)
        count = content.count(old_in_file)

    # new_string adopts the style of the span it replaces: the endings
    # old_string actually used, or the file's dominant style for a single-line
    # match (whose own text says nothing about endings).
    if "\r\n" in old_in_file:
        span_newline = "\r\n"
    elif "\n" in old_in_file:
        span_newline = "\n"
    else:
        span_newline = dominant
    new_in_file = _with_newline(new_string, span_newline)

    if count == 0:
        # Try to help debug: show similar strings
        lines_with_similar = []
        for i, line in enumerate(content.splitlines(), 1):
            # Check if any significant part of old_string is in the line
            if len(old_string) > 10:
                # For longer strings, check first 20 chars
                if old_string[:20] in line or old_string[-20:] in line:
                    lines_with_similar.append(f"  Line {i}: {line[:80]}")
            elif old_string.strip() in line:
                lines_with_similar.append(f"  Line {i}: {line[:80]}")

        msg = f"Error: String not found in '{file_path}'"
        if lines_with_similar:
            msg += "\n\nSimilar content found:\n" + "\n".join(lines_with_similar[:5])
        return ToolFailure(msg)

    if count > 1 and not replace_all:
        # Show where the duplicates are
        lines_with_match = []
        for i, line in enumerate(content.splitlines(), 1):
            if old_string in line:
                lines_with_match.append(f"  Line {i}: {line[:80]}")

        return ToolFailure(
            f"Error: String appears {count} times in '{file_path}'. "
            f"Use replace_all=True to replace all, or provide more context to make it unique.\n\n"
            f"Found at:\n" + "\n".join(lines_with_match[:10])
        )

    # Perform replacement
    if replace_all:
        new_content = content.replace(old_in_file, new_in_file)
        replaced_count = count
    else:
        new_content = content.replace(old_in_file, new_in_file, 1)
        replaced_count = 1

    # Write back
    path.write_bytes(new_content.encode("utf-8"))

    if replace_all and replaced_count > 1:
        return f"Replaced {replaced_count} occurrences in '{file_path}'"
    else:
        return f"Successfully edited '{file_path}'"
