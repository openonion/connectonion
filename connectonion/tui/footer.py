"""
Purpose: Simple footer tips display for terminal UI
LLM-Note:
  Dependencies: imports from [rich.text.Text] | imported by [tui/chat.py, tui/input.py] | tested by [tests/tui/test_footer.py]
  Data flow: Footer(tips) → render() → formats tips as dimmed text with separators
  State/Effects: no state (pure function)
  Integration: exposes Footer(tips: list[str]) with render() → Text | displays help hints at bottom of TUI
  Performance: trivial (string join)
  Errors: none
Footer - Simple tips display.

Usage:
    from connectonion.tui import Footer

    footer = Footer(["? help", "/ commands", "@ contacts"])
    console.print(footer.render())
"""

from rich.text import Text


class Footer:
    """Simple footer - displays what you give it."""

    def __init__(self, tips: list[str]):
        """
        Args:
            tips: List of tips to display
        """
        self.tips = tips

    def render(self) -> Text:
        """Render tips."""
        out = Text()
        for i, tip in enumerate(self.tips):
            out.append(tip, style="dim")
            if i < len(self.tips) - 1:
                out.append("  ", style="dim")
        return out
