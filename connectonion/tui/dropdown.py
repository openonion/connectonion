"""Dropdown - reusable selection list component.

Modern zsh-style dropdown with icons and highlighting.
"""

from dataclasses import dataclass, field
from typing import Any

from rich.text import Text
from rich.table import Table
from rich.console import Group

from .fuzzy import highlight_match


@dataclass
class DropdownItem:
    """Structured item for dropdown display.

    Supports rich metadata for different display styles.

    Usage:
        # Simple item
        item = DropdownItem(display="/today", value="/today")

        # With description (shows on second line or right side)
        item = DropdownItem(
            display="/today",
            value="/today",
            description="Daily email briefing",
            icon="📅"
        )

        # Contact style
        item = DropdownItem(
            display="Davis Baer",
            value="davis@oneupapp.io",
            description="davis@oneupapp.io",
            subtitle="OneUp · founder",
            icon="👤"
        )
    """
    display: str                    # Main text to show
    value: Any                      # Value to return when selected
    score: int = 0                  # Match score for sorting
    positions: list[int] = field(default_factory=list)  # Matched char positions
    description: str = ""           # Secondary text (right side or second line)
    subtitle: str = ""              # Third line or additional context
    icon: str = ""                  # Left icon (emoji or nerd font)
    style: str = ""                 # Rich style for the display text

    @classmethod
    def from_tuple(cls, item: tuple) -> "DropdownItem":
        """Convert old tuple format to DropdownItem for backward compatibility.

        Supports:
            (display, value, score, positions)
            (display, value, score, positions, metadata_dict)
        """
        if isinstance(item, DropdownItem):
            return item

        display, value, score, positions = item[:4]
        metadata = item[4] if len(item) > 4 else {}

        return cls(
            display=display,
            value=value,
            score=score,
            positions=positions or [],
            description=metadata.get("description", ""),
            subtitle=metadata.get("subtitle", ""),
            icon=metadata.get("icon", ""),
            style=metadata.get("style", ""),
        )


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
    Supports DropdownItem for rich metadata display.

    Usage:
        dropdown = Dropdown(max_visible=8)

        # Old tuple format (backward compatible)
        dropdown.set_items([
            ("agent.py", "agent.py", 10, [0,1,2]),
            ("main.py", "main.py", 5, [0,1]),
        ])

        # New DropdownItem format
        dropdown.set_items([
            DropdownItem("/today", "/today", description="Daily briefing", icon="📅"),
            DropdownItem("/inbox", "/inbox", description="Show emails", icon="📥"),
        ])

        dropdown.down()  # Move selection
        selected = dropdown.selected_value  # Get current selection
    """

    def __init__(self, max_visible: int = 8, show_icons: bool = True):
        self.max_visible = max_visible
        self.show_icons = show_icons
        self.items: list[DropdownItem] = []
        self.selected_index = 0

    def set_items(self, items: list):
        """Set items. Accepts DropdownItem or old tuple format."""
        converted = []
        for item in items[:self.max_visible]:
            if isinstance(item, DropdownItem):
                converted.append(item)
            else:
                converted.append(DropdownItem.from_tuple(item))
        self.items = converted
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
            return self.items[self.selected_index].value
        return None

    @property
    def selected_display(self) -> str:
        """Get currently selected display text."""
        if self.items and self.selected_index < len(self.items):
            return self.items[self.selected_index].display
        return ""

    def up(self):
        """Move selection up."""
        if self.items:
            self.selected_index = (self.selected_index - 1) % len(self.items)

    def down(self):
        """Move selection down."""
        if self.items:
            self.selected_index = (self.selected_index + 1) % len(self.items)

    def _get_icon(self, item: DropdownItem) -> str:
        """Get icon for item - use item.icon if set, otherwise infer from filename."""
        if item.icon:
            return item.icon
        if self.show_icons:
            return get_file_icon(item.display)
        return ""

    def render(self) -> Table:
        """Render dropdown as Rich Table.

        Supports multiple display modes based on DropdownItem fields:
        - Simple: just display text with icon
        - With description: display + description on right
        - With subtitle: two-line display

        Selected item has light background for visibility on both light/dark terminals.
        """
        table = Table(show_header=False, box=None, padding=(0, 0), show_edge=False)

        for i, item in enumerate(self.items):
            is_selected = i == self.selected_index
            row = Text()

            # Selection indicator
            if is_selected:
                row.append("  ❯ ", style="bold green")
            else:
                row.append("    ", style="dim")

            # Icon
            icon = self._get_icon(item)
            if icon:
                if is_selected:
                    row.append(f"{icon} ", style="bold")
                else:
                    row.append(f"{icon} ", style="dim")

            # Main display text with highlighting
            display_style = item.style if item.style else ""
            highlighted = highlight_match(item.display, item.positions)
            if display_style:
                highlighted.stylize(display_style)
            row.append_text(highlighted)

            # Description (right side, dimmed)
            if item.description:
                row.append("  ", style="dim")
                row.append(item.description, style="dim italic")

            # Add background to selected row
            if is_selected:
                row.stylize("on bright_black")

            table.add_row(row)

            # Subtitle as second line (only for selected or all items with subtitle)
            if item.subtitle and is_selected:
                subtitle_row = Text()
                subtitle_row.append("        ", style="dim")  # Indent to align with text
                subtitle_row.append(item.subtitle, style="dim")
                if is_selected:
                    subtitle_row.stylize("on bright_black")
                table.add_row(subtitle_row)

        return table
