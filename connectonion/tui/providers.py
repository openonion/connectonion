"""Providers for CommandPalette and Input autocomplete."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from .fuzzy import fuzzy_match


@runtime_checkable
class Provider(Protocol):
    """Protocol for autocomplete providers."""

    def search(self, query: str) -> list[tuple[str, any, int, list[int]]]:
        """Return matches as (display, value, score, positions)."""
        ...


class StaticProvider:
    """Provider for static list of items."""

    def __init__(self, items: list[tuple[str, any]]):
        """
        Args:
            items: List of (display_text, value) tuples
        """
        self.items = items

    def search(self, query: str) -> list[tuple[str, any, int, list[int]]]:
        results = []
        for name, value in self.items:
            matched, score, positions = fuzzy_match(query, name)
            if matched:
                results.append((name, value, score, positions))
        return sorted(results, key=lambda x: -x[2])


class FileProvider:
    """Provider for file system navigation with directory traversal."""

    def __init__(
        self,
        root: Path = None,
        show_hidden: bool = False,
        dirs_only: bool = False,
        files_only: bool = False,
    ):
        self.root = Path(root) if root else Path(".")
        self.show_hidden = show_hidden
        self.dirs_only = dirs_only
        self.files_only = files_only
        self._context = ""  # Current directory for nested navigation

    @property
    def context(self) -> str:
        return self._context

    @context.setter
    def context(self, value: str):
        self._context = value

    def search(self, query: str) -> list[tuple[str, any, int, list[int]]]:
        """Search files in current context directory."""
        base = self.root / self._context if self._context else self.root
        if not base.exists():
            return []

        results = []
        for f in base.iterdir():
            if not self.show_hidden and f.name.startswith('.'):
                continue
            if self.dirs_only and not f.is_dir():
                continue
            if self.files_only and f.is_dir():
                continue

            is_dir = f.is_dir()
            name = f.name + ("/" if is_dir else "")
            matched, score, positions = fuzzy_match(query, name)

            if matched:
                full_path = (self._context + name) if self._context else name
                results.append((name, full_path, score, positions))

        # Sort: directories first, then by score, then alphabetically
        results.sort(key=lambda x: (not x[0].endswith('/'), -x[2], x[0].lower()))
        return results

    def enter(self, path: str) -> bool:
        """Enter a directory. Returns True if successful."""
        if path.endswith('/'):
            self._context = path
            return True
        return False

    def back(self) -> bool:
        """Go up one directory. Returns True if moved up."""
        if self._context:
            parts = self._context.rstrip('/').rsplit('/', 1)
            self._context = parts[0] + '/' if len(parts) > 1 else ""
            return True
        return False