"""
Purpose: Grep tool for content searching
LLM-Note:
  Dependencies: imports from [re, pathlib, typing, .glob_files] | imported by [useful_tools/__init__]
  Data flow: Agent calls grep(pattern) -> searches files -> returns matches
  State/Effects: reads filesystem (no writes)
  Integration: exposes grep(pattern, path, file_pattern, output_mode) function | used as agent tool

Usage:
    grep("def main")                           # Find "def main" in all files
    grep("TODO|FIXME", file_pattern="*.py")   # Find TODOs in Python files
    grep("class.*Agent", output_mode="content") # Show matching lines
    grep("import", output_mode="count")        # Count imports per file
"""

import os
import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Literal, Optional

from ...core.tool_result import ToolFailure
from .glob import IGNORE_DIRS

# One grep from $HOME once walked for 26 minutes in-process (#1453).
MAX_FILES = 20_000
# Reading, not walking, was the cost: 20k files under $HOME held 22 GB.
MAX_FILE_BYTES = 2_000_000


def grep(
    pattern: str,
    path: Optional[str] = None,
    file_pattern: Optional[str] = None,
    output_mode: Literal["files", "content", "count"] = "files",
    context_lines: int = 0,
    ignore_case: bool = False,
    max_results: int = 50,
) -> str:
    """
    Search for content in files using regex.

    Args:
        pattern: Regular expression pattern to search for
        path: File or directory to search in (default: current directory).
            A directory search skips files over 2 MB and stops after 20,000
            files; pass a single file as `path` to search it whatever its size.
        file_pattern: Glob pattern to filter files (e.g., "*.py", "*.ts")
        output_mode:
            - "files": Return only matching file paths (default)
            - "content": Return matching lines with context
            - "count": Return match counts per file
        context_lines: Number of lines to show before/after match (for content mode)
        ignore_case: Case insensitive search
        max_results: Maximum number of results to return

    Returns:
        Search results based on output_mode

    Examples:
        grep("def main")                           # Find "def main" in all files
        grep("TODO|FIXME", file_pattern="*.py")   # Find TODOs in Python files
        grep("class.*Agent", output_mode="content") # Show matching lines
        grep("import", output_mode="count")        # Count imports per file
    """
    base = Path(path) if path else Path.cwd()

    if not base.exists():
        return ToolFailure(f"Error: Path '{base}' does not exist")

    # Compile regex
    flags = re.IGNORECASE if ignore_case else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return ToolFailure(f"Error: Invalid regex pattern: {e}")

    files = [base] if base.is_file() else _walk(base, file_pattern)
    walk_capped = False

    results = []
    total_matches = 0

    for visited, file in enumerate(files):
        if total_matches >= max_results:
            break
        if visited >= MAX_FILES:
            walk_capped = True
            break

        try:
            content = file.read_text(encoding="utf-8", errors="ignore")
            lines = content.splitlines()
        except Exception:
            continue

        file_matches = []
        for i, line in enumerate(lines):
            if regex.search(line):
                file_matches.append((i + 1, line))  # 1-indexed line number

        if not file_matches:
            continue

        rel_path = _relative_path(file, base)

        if output_mode == "files":
            results.append(str(rel_path))
            total_matches += 1

        elif output_mode == "count":
            results.append(f"{rel_path}: {len(file_matches)} matches")
            total_matches += 1

        elif output_mode == "content":
            results.append(f"\n{rel_path}:")
            for line_num, line_text in file_matches[:10]:  # Limit per file
                # Add context if requested
                if context_lines > 0:
                    start = max(0, line_num - 1 - context_lines)
                    end = min(len(lines), line_num + context_lines)
                    for ctx_i in range(start, end):
                        prefix = ">" if ctx_i == line_num - 1 else " "
                        results.append(f"  {prefix} {ctx_i + 1}: {lines[ctx_i]}")
                    results.append("")
                else:
                    results.append(f"  {line_num}: {line_text}")
                total_matches += 1

                if total_matches >= max_results:
                    break

    capped = (f"\n\n... search stopped after {MAX_FILES} files; "
              "narrow `path` or set `file_pattern`") if walk_capped else ""
    if not results:
        return f"No matches found for '{pattern}'{capped}"

    output = "\n".join(results) + capped

    if total_matches >= max_results:
        output += f"\n\n... results truncated at {max_results}"

    return output


def _walk(base: Path, file_pattern: Optional[str]):
    """Yield searchable files lazily, never entering an ignored directory."""
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not _ignored(d))
        for name in sorted(filenames):
            file = Path(dirpath) / name
            if ((file_pattern is None or file.relative_to(base).match(file_pattern)) and _is_text_file(file)
                    and file.is_file() and file.stat().st_size <= MAX_FILE_BYTES):
                yield file


def _ignored(name: str) -> bool:
    return any(name == ignore or ("*" in ignore and fnmatch(name, ignore)) for ignore in IGNORE_DIRS)


def _is_text_file(path: Path) -> bool:
    """Check if file is likely a text file."""
    # Skip binary file extensions
    binary_extensions = {
        ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
        ".zip", ".tar", ".gz", ".rar", ".7z",
        ".mp3", ".mp4", ".wav", ".avi", ".mov",
        ".ttf", ".woff", ".woff2", ".eot",
        ".lock", ".bin", ".dat",
    }
    return path.suffix.lower() not in binary_extensions


def _relative_path(path: Path, base: Path) -> Path:
    """Get relative path, handling edge cases."""
    try:
        return path.relative_to(base)
    except ValueError:
        return path
