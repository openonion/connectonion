"""
Purpose: Glob tool for file pattern matching
LLM-Note:
  Dependencies: imports from [pathlib, typing] | imported by [useful_tools/__init__, grep]
  Data flow: Agent calls glob(pattern) -> searches directory -> returns matching paths
  State/Effects: reads filesystem (no writes)
  Integration: exposes glob(pattern, path) function | used as agent tool | shared IGNORE_DIRS constant

Usage:
    glob("**/*.py")           # All Python files
    glob("src/**/*.tsx")      # All TSX files in src/
    glob("**/test_*.py")      # All test files
    glob("*.md", "docs")      # Markdown files in docs/
"""

from pathlib import Path
from typing import Optional

IGNORE_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    ".idea",
    ".vscode",
    "*.egg-info",
}


def glob(pattern: str, path: Optional[str] = None) -> str:
    """
    Search for files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., "**/*.py", "src/**/*.ts")
        path: Directory to search in (default: current directory)

    Returns:
        Matching file paths, one per line, sorted by modification time (newest first)

    Examples:
        glob("**/*.py")           # All Python files
        glob("src/**/*.tsx")      # All TSX files in src/
        glob("**/test_*.py")      # All test files
        glob("*.md", "docs")      # Markdown files in docs/
    """
    base = Path(path) if path else Path.cwd()

    if not base.exists():
        return f"Error: Path '{base}' does not exist"

    if not base.is_dir():
        return f"Error: Path '{base}' is not a directory"

    matches = []
    for p in base.glob(pattern):
        if p.is_file() and not _should_ignore(p):
            matches.append(p)

    if not matches:
        return f"No files found matching '{pattern}'"

    # Sort by modification time (newest first)
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # Format output
    results = []
    for p in matches[:100]:  # Limit to 100 results
        rel_path = p.relative_to(base) if path else p.relative_to(Path.cwd())
        results.append(str(rel_path))

    output = "\n".join(results)

    if len(matches) > 100:
        output += f"\n\n... and {len(matches) - 100} more files"

    return output


def _should_ignore(path: Path) -> bool:
    """Check if path should be ignored."""
    parts = path.parts
    for part in parts:
        if part in IGNORE_DIRS:
            return True
        # Handle patterns like *.egg-info
        for ignore in IGNORE_DIRS:
            if "*" in ignore and Path(part).match(ignore):
                return True
    return False
