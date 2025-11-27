"""StatusBar - Powerline-style info bar with segments.

Creates a professional terminal prompt bar like powerlevel10k.
"""

from dataclasses import dataclass
from rich.text import Text


# Powerline characters
ARROW_RIGHT = ""  # U+E0B0 - requires powerline font
ARROW_RIGHT_THIN = ""  # U+E0B1
ARROW_LEFT = ""  # U+E0B2
ARROW_LEFT_THIN = ""  # U+E0B3

# Fallback for terminals without powerline fonts
ARROW_FALLBACK = "▶"

# Progress bar characters
PROGRESS_FILLED = "█"
PROGRESS_EMPTY = "░"


@dataclass
class ProgressSegment:
    """A progress bar segment for StatusBar.

    Usage:
        from connectonion.tui import StatusBar, ProgressSegment

        status = StatusBar([
            ("🤖", "co/gemini-2.5-pro", "magenta"),
            ProgressSegment(percent=78, bg_color="green"),
        ])
    """
    percent: float  # 0-100, how much is USED
    bg_color: str = "green"
    width: int = 10
    show_percent: bool = True

    def render(self) -> str:
        """Render progress bar text."""
        pct = max(0, min(100, self.percent))
        filled = int(self.width * pct / 100)
        empty = self.width - filled
        bar = PROGRESS_FILLED * filled + PROGRESS_EMPTY * empty
        if self.show_percent:
            return f"{bar} {int(pct)}%"
        return bar


class StatusBar:
    """Powerline-style status bar with colored segments.

    Supports both text segments and progress bar segments.

    Usage:
        from connectonion.tui import StatusBar, ProgressSegment

        # Text segments only
        bar = StatusBar([
            ("🤖", "co/gemini-2.5-pro", "magenta"),
            ("", "main", "blue"),
        ])

        # With progress bar for context window
        bar = StatusBar([
            ("🤖", "co/gemini-2.5-pro", "magenta"),
            ProgressSegment(percent=78, bg_color="green"),
        ])
        console.print(bar.render())

    Output (with powerline font):
        🤖 co/gemini-2.5-pro  ███████░░░ 78%
    """

    def __init__(
        self,
        segments: list,
        use_powerline: bool = True,
    ):
        """
        Args:
            segments: List of (icon, text, bg_color) tuples or ProgressSegment
            use_powerline: Use powerline arrow chars (requires font)
        """
        self.segments = segments
        self.use_powerline = use_powerline

    def _get_bg_color(self, segment) -> str:
        """Get background color from segment."""
        if isinstance(segment, ProgressSegment):
            return segment.bg_color
        return segment[2]

    def _render_segment_content(self, segment) -> str:
        """Render segment content text."""
        if isinstance(segment, ProgressSegment):
            return f" {segment.render()} "
        icon, text, _ = segment
        return f" {icon} {text} " if icon else f" {text} "

    def render(self) -> Text:
        """Render the status bar."""
        result = Text()

        for i, segment in enumerate(self.segments):
            bg_color = self._get_bg_color(segment)
            content = self._render_segment_content(segment)

            # Add segment with background
            result.append(content, style=f"bold white on {bg_color}")

            # Add arrow separator
            if i < len(self.segments) - 1:
                next_bg = self._get_bg_color(self.segments[i + 1])
                if self.use_powerline:
                    result.append(ARROW_RIGHT, style=f"{bg_color} on {next_bg}")
                else:
                    result.append(ARROW_FALLBACK, style=f"{bg_color} on {next_bg}")
            else:
                # Final arrow to terminal background
                if self.use_powerline:
                    result.append(ARROW_RIGHT, style=f"{bg_color}")
                else:
                    result.append(ARROW_FALLBACK, style=f"{bg_color}")

        return result


class SimpleStatusBar:
    """Simpler status bar without powerline fonts.

    Uses brackets and pipes instead of arrows.

    Usage:
        bar = SimpleStatusBar([
            ("🤖", "co/gemini-2.5-pro", "magenta"),
            ("📊", "50%", "green"),
        ])
        console.print(bar.render())

    Output:
        [🤖 co/gemini-2.5-pro] [📊 50%]
    """

    def __init__(self, segments: list[tuple[str, str, str]]):
        self.segments = segments

    def render(self) -> Text:
        result = Text()

        for i, (icon, text, color) in enumerate(self.segments):
            if i > 0:
                result.append(" ")

            result.append("[", style="dim")
            if icon:
                result.append(f"{icon} ", style=color)
            result.append(text, style=f"bold {color}")
            result.append("]", style="dim")

        return result
