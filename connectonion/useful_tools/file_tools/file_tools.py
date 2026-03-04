"""
Purpose: FileTools class with read-before-edit state tracking and permission control
LLM-Note:
  Dependencies: imports from [hashlib, pathlib, typing, .read_file, .edit, .multi_edit, .write_file, .glob_files, .grep_files]
  Data flow: Agent uses FileTools instance -> tracks read snapshots -> validates before edit
  State/Effects: maintains _snapshots dict (path → content hash) for stale-read detection
  Integration: exposes FileTools class | used as agent tool bundle
  Errors: edit returns error if file not read first | edit returns error if file changed since read

Usage:
    FileTools()                    # full access with read-before-edit tracking
    FileTools(permission="read")   # read-only mode
"""

import hashlib
from pathlib import Path
from typing import Optional, List, Literal

from .read import read_file as _read_file
from .edit import edit as _edit
from .multi_edit import multi_edit as _multi_edit, EditOperation
from .write import write as _write
from .glob import glob as _glob
from .grep import grep as _grep


class FileTools:
    """File operation tools with read-before-edit tracking and permission control.

    Features:
    - Tracks file snapshots (MD5 hash) when read
    - Validates file hasn't changed before edit (stale-read protection)
    - Permission-based access control (write/read)

    Usage:
        FileTools()                    # full access (default)
        FileTools(permission="read")   # read-only
    """

    def __init__(self, permission: Literal["write", "read"] = "write"):
        """Initialize FileTools.

        Args:
            permission: "write" (full access) or "read" (read-only)
        """
        self._permission = permission
        self._snapshots: dict[str, str] = {}  # path → MD5 hash

    def read_file(
        self, path: str, offset: Optional[int] = None, limit: Optional[int] = None
    ) -> str:
        """Read and return the contents of a file with line numbers.

        Automatically tracks file snapshot for later edit validation.

        Args:
            path: Path to the file to read
            offset: Line number to start from (1-indexed)
            limit: Number of lines to read

        Returns:
            File contents with line numbers
        """
        result = _read_file(path, offset, limit)

        # Track snapshot for edit validation (only if read succeeded)
        if not result.startswith("Error:"):
            file_path = Path(path)
            if file_path.exists() and file_path.is_file():
                content = file_path.read_text(encoding="utf-8", errors="replace")
                self._snapshots[path] = hashlib.md5(content.encode()).hexdigest()

        return result

    def glob(self, pattern: str, path: Optional[str] = None) -> str:
        """Search for files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., "**/*.py", "src/**/*.ts")
            path: Directory to search in (default: current directory)

        Returns:
            Matching file paths, one per line, sorted by modification time
        """
        return _glob(pattern, path)

    def grep(
        self,
        pattern: str,
        path: Optional[str] = None,
        file_pattern: Optional[str] = None,
        output_mode: Literal["files", "content", "count"] = "files",
        context_lines: int = 0,
        ignore_case: bool = False,
        max_results: int = 50,
    ) -> str:
        """Search for content in files using regex.

        Args:
            pattern: Regular expression pattern to search for
            path: File or directory to search in (default: current directory)
            file_pattern: Glob pattern to filter files (e.g., "*.py")
            output_mode: "files" | "content" | "count"
            context_lines: Lines to show before/after match (content mode)
            ignore_case: Case insensitive search
            max_results: Maximum number of results

        Returns:
            Search results based on output_mode
        """
        return _grep(
            pattern, path, file_pattern, output_mode, context_lines, ignore_case, max_results
        )

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        """Replace a string in a file with precise matching.

        Validates:
        1. Permission (returns error if read-only)
        2. File was read first (returns error if not in snapshots)
        3. File hasn't changed since read (stale-read protection)

        Args:
            file_path: Path to the file to edit
            old_string: Exact string to replace (must be unique in file)
            new_string: String to replace with
            replace_all: If True, replace all occurrences

        Returns:
            Success message or error description
        """
        if self._permission == "read":
            return "Error: Permission denied - FileTools is in read-only mode"

        # Check if file was read first
        if file_path not in self._snapshots:
            return f"Error: Read '{file_path}' before editing (use read_file first)"

        # Check if file changed since read (stale-read protection)
        path = Path(file_path)
        if not path.exists():
            return f"Error: File '{file_path}' no longer exists"

        current_content = path.read_text(encoding="utf-8", errors="replace")
        current_hash = hashlib.md5(current_content.encode()).hexdigest()

        if current_hash != self._snapshots[file_path]:
            # File changed externally - invalidate snapshot
            del self._snapshots[file_path]
            return f"Error: '{file_path}' changed since last read - re-read it first"

        # Perform the edit
        result = _edit(file_path, old_string, new_string, replace_all)

        # Update snapshot if edit succeeded
        if not result.startswith("Error:"):
            new_content = path.read_text(encoding="utf-8", errors="replace")
            self._snapshots[file_path] = hashlib.md5(new_content.encode()).hexdigest()

        return result

    def multi_edit(self, file_path: str, edits: List[EditOperation]) -> str:
        """Apply multiple string replacements to a file atomically.

        Validates:
        1. Permission (returns error if read-only)
        2. File was read first
        3. File hasn't changed since read

        Args:
            file_path: Path to the file to edit
            edits: List of {old_string, new_string, replace_all?} operations

        Returns:
            Success message or error description
        """
        if self._permission == "read":
            return "Error: Permission denied - FileTools is in read-only mode"

        # Check if file was read first
        if file_path not in self._snapshots:
            return f"Error: Read '{file_path}' before editing (use read_file first)"

        # Check if file changed since read
        path = Path(file_path)
        if not path.exists():
            return f"Error: File '{file_path}' no longer exists"

        current_content = path.read_text(encoding="utf-8", errors="replace")
        current_hash = hashlib.md5(current_content.encode()).hexdigest()

        if current_hash != self._snapshots[file_path]:
            del self._snapshots[file_path]
            return f"Error: '{file_path}' changed since last read - re-read it first"

        # Perform multi-edit
        result = _multi_edit(file_path, edits)

        # Update snapshot if edit succeeded
        if not result.startswith("Error:"):
            new_content = path.read_text(encoding="utf-8", errors="replace")
            self._snapshots[file_path] = hashlib.md5(new_content.encode()).hexdigest()

        return result

    def write(self, path: str, content: str) -> str:
        """Write content to a file (full overwrite).

        Note: write() does NOT require prior read_file() since it's a full overwrite.
        Primarily for creating new files. For modifying existing files, use edit().

        Args:
            path: File path to write to
            content: Complete file content

        Returns:
            Success message or error description
        """
        if self._permission == "read":
            return "Error: Permission denied - FileTools is in read-only mode"

        # write() is full overwrite - no snapshot check needed
        result = _write(path, content)

        # Track snapshot after write (for subsequent edits)
        if not result.startswith("Error:"):
            file_path = Path(path)
            if file_path.exists() and file_path.is_file():
                content_on_disk = file_path.read_text(encoding="utf-8", errors="replace")
                self._snapshots[path] = hashlib.md5(content_on_disk.encode()).hexdigest()

        return result
