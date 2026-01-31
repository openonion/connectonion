"""Edit tool for precise string replacement."""

from pathlib import Path


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
        return f"Error: File '{file_path}' does not exist"

    if not path.is_file():
        return f"Error: '{file_path}' is not a file"

    content = path.read_text(encoding="utf-8")

    # Check if old_string exists
    count = content.count(old_string)

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
            msg += f"\n\nSimilar content found:\n" + "\n".join(lines_with_similar[:5])
        return msg

    if count > 1 and not replace_all:
        # Show where the duplicates are
        lines_with_match = []
        for i, line in enumerate(content.splitlines(), 1):
            if old_string in line:
                lines_with_match.append(f"  Line {i}: {line[:80]}")

        return (
            f"Error: String appears {count} times in '{file_path}'. "
            f"Use replace_all=True to replace all, or provide more context to make it unique.\n\n"
            f"Found at:\n" + "\n".join(lines_with_match[:10])
        )

    # Perform replacement
    if replace_all:
        new_content = content.replace(old_string, new_string)
        replaced_count = count
    else:
        new_content = content.replace(old_string, new_string, 1)
        replaced_count = 1

    # Write back
    path.write_text(new_content, encoding="utf-8")

    if replace_all and replaced_count > 1:
        return f"Replaced {replaced_count} occurrences in '{file_path}'"
    else:
        return f"Successfully edited '{file_path}'"
