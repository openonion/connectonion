"""
Purpose: Atomic multiple string replacements in a single file (like Claude Code's MultiEdit)
LLM-Note:
  Dependencies: imports from [pathlib, typing] | imported by [co_ai.tools.__init__]
  Data flow: Agent calls multi_edit(file_path, edits) -> validates all edits -> applies sequentially -> returns status
  State/Effects: reads and writes file on filesystem | atomic (all succeed or none applied)
  Integration: exposes multi_edit(file_path, edits) function | used as agent tool
  Errors: returns error if file not found | returns error if any old_string not found | rolls back on failure

Usage:
    multi_edit("app.py", [
        {"old_string": "def foo():", "new_string": "def bar():"},
        {"old_string": "return None", "new_string": "return True"},
    ])
"""

from pathlib import Path
from typing import List, TypedDict, Optional


class EditOperation(TypedDict, total=False):
    """Single edit operation."""
    old_string: str              # Required: exact string to replace
    new_string: str              # Required: replacement string
    replace_all: bool            # Optional: replace all occurrences (default: False)


def multi_edit(
    file_path: str,
    edits: List[EditOperation],
) -> str:
    """
    Apply multiple string replacements to a file atomically.

    All edits succeed or none are applied. Edits are applied sequentially,
    so earlier edits affect the text that later edits search for.

    Args:
        file_path: Path to the file to edit
        edits: List of edit operations, each with:
            - old_string: Exact string to replace
            - new_string: Replacement string
            - replace_all: If True, replace all occurrences (default: False)

    Returns:
        Success message or error description

    Examples:
        multi_edit("app.py", [
            {"old_string": "def foo():", "new_string": "def bar():"},
            {"old_string": "foo()", "new_string": "bar()", "replace_all": True},
        ])
    """
    path = Path(file_path)

    if not path.exists():
        return f"Error: File '{file_path}' does not exist"

    if not path.is_file():
        return f"Error: '{file_path}' is not a file"

    if not edits:
        return "Error: No edits provided"

    # Read original content
    original_content = path.read_text(encoding="utf-8")
    content = original_content

    # Validate and apply edits
    applied = []
    for i, edit in enumerate(edits):
        old_string = edit.get("old_string", "")
        new_string = edit.get("new_string", "")
        replace_all = edit.get("replace_all", False)

        if not old_string:
            return f"Error: Edit {i+1} missing 'old_string'"

        # Check if old_string exists in current content
        count = content.count(old_string)

        if count == 0:
            # Show what edits were successful before failure
            if applied:
                applied_msg = "\n".join([f"  {j+1}. Replaced '{e['old']}'" for j, e in enumerate(applied)])
                return (
                    f"Error: Edit {i+1} failed - string not found after previous edits.\n"
                    f"Looking for: {repr(old_string[:100])}\n\n"
                    f"Successfully applied before failure:\n{applied_msg}\n\n"
                    f"No changes were saved (atomic operation)."
                )
            return f"Error: Edit {i+1} - string not found in '{file_path}': {repr(old_string[:100])}"

        if count > 1 and not replace_all:
            return (
                f"Error: Edit {i+1} - string appears {count} times. "
                f"Use replace_all=True or provide more context.\n"
                f"String: {repr(old_string[:100])}"
            )

        # Apply this edit
        if replace_all:
            content = content.replace(old_string, new_string)
            applied.append({"old": old_string[:50], "count": count})
        else:
            content = content.replace(old_string, new_string, 1)
            applied.append({"old": old_string[:50], "count": 1})

    # All edits validated and applied in memory - now write to file
    path.write_text(content, encoding="utf-8")

    # Build success message
    total_replacements = sum(e["count"] for e in applied)
    if len(edits) == 1:
        return f"Successfully edited '{file_path}'"
    return f"Successfully applied {len(edits)} edits ({total_replacements} replacements) to '{file_path}'"
