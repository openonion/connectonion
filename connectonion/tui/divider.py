"""Divider - Simple horizontal line separator.

A minimal line to separate sections in terminal UI.
"""

from rich.text import Text


class Divider:
    """Simple horizontal divider line.

    Usage:
        from connectonion.tui import Divider

        divider = Divider()
        console.print(divider.render())

        # Custom width
        divider = Divider(width=40)
        console.print(divider.render())

    Output:
        ────────────────────────────────────
    """

    def __init__(self, width: int = 40, char: str = "─", style: str = "dim"):
        """
        Args:
            width: Width of the divider line
            char: Character to use for the line
            style: Rich style for the line
        """
        self.width = width
        self.char = char
        self.style = style

    def render(self) -> Text:
        """Render the divider line."""
        return Text(self.char * self.width, style=self.style)
