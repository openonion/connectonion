"""Dropdown - reusable selection list component.

Modern zsh-style dropdown with icons and highlighting.
"""

from rich.text import Text
from rich.table import Table
from rich.console import Group

from .fuzzy import highlight_match

# File type icons (requires Nerd Font for best results, fallback to unicode)
ICONS = {
    "folder": "📁",
    "python": "🐍",
    "javascript": "📜",
    "typescript": "📘",
    "json": "📋",
    "markdown": "📝",
    "yaml": "⚙️",
    "default": "📄",
}


def get_file_icon(name: str) -> str:
    """Get icon for file based on extension."""
    if name.endswith('/'):
        return ICONS["folder"]
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ""
    if ext == "py":
        return ICONS["python"]
    elif ext in ("js", "jsx"):
        return ICONS["javascript"]
    elif ext in ("ts", "tsx"):
        return ICONS["typescript"]
    elif ext == "json":
        return ICONS["json"]
    elif ext in ("md", "mdx"):
        return ICONS["markdown"]
    elif ext in ("yml", "yaml"):
        return ICONS["yaml"]
    return ICONS["default"]


class Dropdown:
    """Dropdown selection list with keyboard navigation.

    Modern zsh-style with icons and fuzzy match highlighting.

    Usage:
        dropdown = Dropdown(max_visible=8)
        dropdown.set_items([
            ("agent.py", "agent.py", 10, [0,1,2]),
            ("main.py", "main.py", 5, [0,1]),
        ])
        dropdown.down()  # Move selection
        selected = dropdown.selected_value  # Get current selection
    """

    def __init__(self, max_visible: int = 8, show_icons: bool = True):
        self.max_visible = max_visible
        self.show_icons = show_icons
        self.items: list[tuple[str, any, int, list[int]]] = []
        self.selected_index = 0

    def set_items(self, items: list[tuple[str, any, int, list[int]]]):
        """Set items as (display, value, score, match_positions)."""
        self.items = items[:self.max_visible]
        self.selected_index = 0

    def clear(self):
        """Clear all items."""
        self.items = []
        self.selected_index = 0

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0

    @property
    def selected_value(self):
        """Get currently selected value."""
        if self.items and self.selected_index < len(self.items):
            return self.items[self.selected_index][1]
        return None

    @property
    def selected_display(self) -> str:
        """Get currently selected display text."""
        if self.items and self.selected_index < len(self.items):
            return self.items[self.selected_index][0]
        return ""

    def up(self):
        """Move selection up."""
        if self.items:
            self.selected_index = (self.selected_index - 1) % len(self.items)

    def down(self):
        """Move selection down."""
        if self.items:
            self.selected_index = (self.selected_index + 1) % len(self.items)

    def render(self) -> Table:
        """Render dropdown as Rich Table.

        Selected item has light background for visibility on both light/dark terminals.
        """
        table = Table(show_header=False, box=None, padding=(0, 0), show_edge=False)

        for i, (display, value, score, positions) in enumerate(self.items):
            is_selected = i == self.selected_index
            row = Text()

            # Selection indicator
            if is_selected:
                row.append("  ❯ ", style="bold green")
            else:
                row.append("    ", style="dim")

            # File icon
            if self.show_icons:
                icon = get_file_icon(display)
                if is_selected:
                    row.append(f"{icon} ", style="bold")
                else:
                    row.append(f"{icon} ", style="dim")

            # Highlighted filename
            highlighted = highlight_match(display, positions)
            row.append_text(highlighted)

            # Add background to selected row
            if is_selected:
                # Apply background to entire row for visibility
                row.stylize("on bright_black")

            table.add_row(row)

        return table
