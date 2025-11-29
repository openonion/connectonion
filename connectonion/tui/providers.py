"""Providers for CommandPalette and Input autocomplete."""

from pathlib import Path
from typing import Protocol, runtime_checkable, Union

from .fuzzy import fuzzy_match
from .dropdown import DropdownItem


@runtime_checkable
class Provider(Protocol):
    """Protocol for autocomplete providers."""

    def search(self, query: str) -> list[Union[DropdownItem, tuple]]:
        """Return matches as DropdownItem or (display, value, score, positions) tuple."""
        ...


class StaticProvider:
    """Provider for static list of items.

    Supports multiple input formats:
    - (display, value) - simple tuple
    - (display, value, description) - with description
    - (display, value, description, icon) - with icon
    - DropdownItem - full control

    Usage:
        # Simple commands
        provider = StaticProvider([
            ("/today", "/today"),
            ("/inbox", "/inbox"),
        ])

        # With descriptions
        provider = StaticProvider([
            ("/today", "/today", "Daily email briefing"),
            ("/inbox", "/inbox", "Show recent emails"),
        ])

        # With icons
        provider = StaticProvider([
            ("/today", "/today", "Daily briefing", "📅"),
            ("/inbox", "/inbox", "Show emails", "📥"),
        ])
    """

    def __init__(self, items: list):
        """
        Args:
            items: List of tuples or DropdownItem objects
        """
        self.items = self._normalize_items(items)

    def _normalize_items(self, items: list) -> list[tuple]:
        """Convert items to normalized format (display, value, description, icon)."""
        normalized = []
        for item in items:
            if isinstance(item, DropdownItem):
                normalized.append((item.display, item.value, item.description, item.icon))
            elif len(item) == 2:
                normalized.append((item[0], item[1], "", ""))
            elif len(item) == 3:
                normalized.append((item[0], item[1], item[2], ""))
            elif len(item) >= 4:
                normalized.append((item[0], item[1], item[2], item[3]))
        return normalized

    def search(self, query: str) -> list[DropdownItem]:
        results = []
        for display, value, description, icon in self.items:
            matched, score, positions = fuzzy_match(query, display)
            if matched:
                results.append(DropdownItem(
                    display=display,
                    value=value,
                    score=score,
                    positions=positions,
                    description=description,
                    icon=icon,
                ))
        return sorted(results, key=lambda x: -x.score)


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

    def search(self, query: str) -> list[DropdownItem]:
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
                # Icons are handled by Dropdown based on filename
                results.append(DropdownItem(
                    display=name,
                    value=full_path,
                    score=score,
                    positions=positions,
                ))

        # Sort: directories first, then by score, then alphabetically
        results.sort(key=lambda x: (not x.display.endswith('/'), -x.score, x.display.lower()))
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