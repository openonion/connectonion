"""Input - smart input component with triggers and autocomplete.

Clean, minimal design that works on light and dark terminals.
Inspired by powerlevel10k terminal prompts.
"""

import random
from typing import Optional
from rich.console import Console, Group
from rich.text import Text
from rich.live import Live

from .keys import read_key
from .dropdown import Dropdown
from .providers import FileProvider


# Color palette - works on both light and dark terminals
COLORS = {
    "prompt": "bold magenta",
    "text": "default",  # User input in default terminal color
    "filter": "bold green",
    "cursor": "reverse",
    "hint": "dim",
    "tip": "dim italic",
}

# Global counter for rotating tips
_input_count = 0


class Input:
    """Smart input with trigger-based autocomplete.

    Usage:
        from connectonion.tui import Input, FileProvider

        # Simple
        text = Input().run()

        # With autocomplete
        text = Input(triggers={"@": FileProvider()}).run()

        # With hints (always visible) and tips (rotating)
        text = Input(
            hints=["/ commands", "@ contacts", "Enter submit"],
            tips=["Try /today for briefing", "Join our Discord!"],
            divider=True,
        ).run()
    """

    def __init__(
        self,
        prompt: str = None,
        triggers: dict = None,
        hints: list[str] = None,
        tips: list[str] = None,
        divider: bool = False,
        max_visible: int = 8,
        console: Console = None,
        style: str = "modern",
    ):
        """
        Args:
            prompt: Custom prompt text
            triggers: Dict of {char: Provider} for autocomplete
            hints: Always-visible keyboard hints (e.g., ["/ commands", "Enter submit"])
            tips: Rotating tips shown occasionally (e.g., ["Try /today", "Join Discord"])
            divider: Add horizontal dividers around input
            max_visible: Max dropdown items
            console: Rich console
            style: "modern", "minimal", or "classic"
        """
        self.prompt = prompt
        self.triggers = triggers or {}
        self.hints = hints
        self.tips = tips
        self.divider = divider
        self.max_visible = max_visible
        self.console = console or Console()
        self.style = style

        # State
        self.buffer = ""
        self.active_trigger = None
        self.filter_text = ""
        self.dropdown = Dropdown(max_visible=max_visible)

    def _render_prompt(self) -> Text:
        """Render prompt based on style."""
        if self.prompt:
            return Text(self.prompt)

        prompts = {"modern": "❯ ", "minimal": "> ", "classic": "$ "}
        return Text(prompts.get(self.style, "❯ "), style=COLORS["prompt"])

    def _get_rotating_tip(self) -> str | None:
        """Get a rotating tip (shows every 4 inputs, 60% chance)."""
        global _input_count
        if not self.tips:
            return None
        # Show tip every 4 rounds with 60% probability
        if _input_count % 4 == 0 and random.random() < 0.6:
            return self.tips[(_input_count // 4) % len(self.tips)]
        return None

    def _render(self) -> Group:
        """Render the input UI."""
        parts = []

        # Top divider (very dim solid line, full width)
        if self.divider:
            width = self.console.width or 80
            parts.append(Text("─" * width, style="dim bright_black"))

        # Input line: prompt + buffer + filter + cursor
        line = self._render_prompt()
        if self.buffer:
            line.append(self.buffer)  # Default terminal color
        if self.active_trigger:
            line.append(self.filter_text, style=COLORS["filter"])
        line.append(" ", style=COLORS["cursor"])
        parts.append(line)

        # Dropdown
        if self.active_trigger and not self.dropdown.is_empty:
            parts.append(Text())
            parts.append(self.dropdown.render())

        # Bottom divider (very dim solid line, full width)
        if self.divider:
            width = self.console.width or 80
            parts.append(Text("─" * width, style="dim bright_black"))

        # Hints (always visible, under divider)
        if self.hints:
            hint_line = Text()
            for i, hint in enumerate(self.hints):
                hint_line.append(hint, style=COLORS["hint"])
                if i < len(self.hints) - 1:
                    hint_line.append("  ")
            parts.append(hint_line)

        # Rotating tip (occasional, under hints)
        tip = self._get_rotating_tip()
        if tip:
            parts.append(Text(tip, style=COLORS["tip"]))

        return Group(*parts)

    def _accept_selection(self) -> bool:
        """Accept dropdown selection. Returns True if navigating directory."""
        value = self.dropdown.selected_value
        if value is None:
            return False

        # Directory navigation for FileProvider
        if isinstance(value, str) and value.endswith('/'):
            provider = self.triggers.get(self.active_trigger)
            if isinstance(provider, FileProvider):
                provider.enter(value)
                self.filter_text = ""
                self._update_dropdown()
                return True

        # Accept selection
        if self.active_trigger and self.buffer.endswith(self.active_trigger):
            self.buffer = self.buffer[:-len(self.active_trigger)]
        self.buffer += str(value)
        self._exit_autocomplete()
        return False

    def _update_dropdown(self):
        """Update dropdown from provider."""
        provider = self.triggers.get(self.active_trigger)
        if provider:
            self.dropdown.set_items(provider.search(self.filter_text))
        else:
            self.dropdown.clear()

    def _exit_autocomplete(self):
        """Exit autocomplete mode."""
        self.active_trigger = None
        self.filter_text = ""
        self.dropdown.clear()
        for provider in self.triggers.values():
            if isinstance(provider, FileProvider):
                provider.context = ""

    def run(self) -> str:
        """Run input loop. Returns entered text."""
        global _input_count
        _input_count += 1

        with Live(self._render(), console=self.console, auto_refresh=False) as live:
            while True:
                key = read_key()

                # Enter - submit or accept selection
                if key in ('\r', '\n'):
                    if self.active_trigger:
                        if not self.dropdown.is_empty:
                            if self._accept_selection():
                                live.update(self._render(), refresh=True)
                                continue
                            live.update(self._render(), refresh=True)
                        else:
                            self._exit_autocomplete()
                            live.update(self._render(), refresh=True)
                    else:
                        return self.buffer

                # Tab - accept selection
                elif key == '\t':
                    if self.active_trigger and not self.dropdown.is_empty:
                        if self._accept_selection():
                            live.update(self._render(), refresh=True)
                            continue
                        live.update(self._render(), refresh=True)

                # Escape - cancel autocomplete
                elif key == 'esc':
                    if self.active_trigger:
                        if self.buffer.endswith(self.active_trigger):
                            self.buffer = self.buffer[:-1]
                        self._exit_autocomplete()
                        live.update(self._render(), refresh=True)

                # Ctrl+C / Ctrl+D
                elif key == '\x03':
                    raise KeyboardInterrupt()
                elif key == '\x04':
                    raise EOFError()

                # Backspace
                elif key in ('\x7f', '\x08'):
                    if self.active_trigger:
                        if self.filter_text:
                            self.filter_text = self.filter_text[:-1]
                            self._update_dropdown()
                        else:
                            provider = self.triggers.get(self.active_trigger)
                            if isinstance(provider, FileProvider) and provider.context:
                                provider.back()
                                self._update_dropdown()
                            else:
                                if self.buffer.endswith(self.active_trigger):
                                    self.buffer = self.buffer[:-1]
                                self._exit_autocomplete()
                        live.update(self._render(), refresh=True)
                    elif self.buffer:
                        self.buffer = self.buffer[:-1]
                        live.update(self._render(), refresh=True)

                # Arrow keys
                elif key == 'up' and self.active_trigger:
                    self.dropdown.up()
                    live.update(self._render(), refresh=True)
                elif key == 'down' and self.active_trigger:
                    self.dropdown.down()
                    live.update(self._render(), refresh=True)

                # Trigger char
                elif key in self.triggers:
                    self.active_trigger = key
                    self.filter_text = ""
                    self.buffer += key
                    self._update_dropdown()
                    live.update(self._render(), refresh=True)

                # Regular input
                elif key.isprintable():
                    if self.active_trigger:
                        self.filter_text += key
                        self._update_dropdown()
                    else:
                        self.buffer += key
                    live.update(self._render(), refresh=True)
