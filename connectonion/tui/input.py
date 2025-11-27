"""Input - smart input component with triggers and autocomplete.

Clean, minimal design that works on light and dark terminals.
Inspired by powerlevel10k terminal prompts.
"""

from rich.console import Console, Group
from rich.text import Text
from rich.live import Live

from .keys import read_key
from .dropdown import Dropdown
from .providers import FileProvider


# Color palette - works on both light and dark terminals
COLORS = {
    "prompt_arrow": "bold magenta",
    "prompt_icon": "bold blue",
    "input_text": "",  # Default terminal color
    "filter_text": "bold green",
    "cursor_block": "reverse",
    "tip": "dim",
}


class Input:
    """Smart input with trigger-based autocomplete.

    Styled like modern zsh terminals (powerlevel10k).

    Usage:
        from connectonion.tui import Input, FileProvider

        # Simple input
        text = Input().run()

        # With @ file autocomplete
        text = Input(triggers={"@": FileProvider()}).run()

        # With multiple triggers
        text = Input(triggers={
            "@": FileProvider(),
            "/": StaticProvider([("/help", "/help"), ("/exit", "/exit")]),
        }).run()

        # With tip
        text = Input(tip="@ files, / commands").run()
    """

    def __init__(
        self,
        prompt: str = None,
        triggers: dict = None,
        tip: str = None,
        max_visible: int = 8,
        console: Console = None,
        style: str = "modern",  # "modern", "minimal", "classic"
    ):
        """
        Args:
            prompt: Custom prompt (default: modern arrow style)
            triggers: Dict of {char: Provider} for autocomplete triggers
            tip: Help text shown below input
            max_visible: Max dropdown items to show
            console: Rich console instance
            style: Visual style - "modern" (default), "minimal", "classic"
        """
        self.custom_prompt = prompt
        self.triggers = triggers or {}
        self.tip = tip
        self.max_visible = max_visible
        self.console = console or Console()
        self.style = style

        # State
        self.buffer = ""
        self.active_trigger = None
        self.filter_text = ""
        self.dropdown = Dropdown(max_visible=max_visible)

    def _get_provider(self):
        """Get provider for active trigger."""
        if self.active_trigger:
            return self.triggers.get(self.active_trigger)
        return None

    def _update_dropdown(self):
        """Update dropdown items from provider."""
        provider = self._get_provider()
        if provider:
            results = provider.search(self.filter_text)
            self.dropdown.set_items(results)
        else:
            self.dropdown.clear()

    def _render_prompt(self) -> Text:
        """Render the prompt part based on style."""
        prompt = Text()

        if self.custom_prompt:
            prompt.append(self.custom_prompt)
            return prompt

        if self.style == "modern":
            # Powerlevel10k-like: ❯ or arrow
            prompt.append("❯ ", style=COLORS["prompt_arrow"])
        elif self.style == "minimal":
            # Simple arrow
            prompt.append("> ", style=COLORS["prompt_arrow"])
        else:  # classic
            prompt.append("$ ", style=COLORS["prompt_icon"])

        return prompt

    def _render(self):
        """Render input line and dropdown.

        No Panel wrapping - clean minimal design like powerlevel10k.
        """
        parts = []

        # Build input line
        input_line = Text()

        # Prompt
        input_line.append_text(self._render_prompt())

        # Buffer text
        input_line.append(self.buffer, style=COLORS["input_text"])

        # Filter text (when in autocomplete mode)
        if self.active_trigger:
            input_line.append(self.filter_text, style=COLORS["filter_text"])

        # Cursor (block style)
        input_line.append(" ", style=COLORS["cursor_block"])

        parts.append(input_line)

        # Dropdown (if active and has items)
        if self.active_trigger and not self.dropdown.is_empty:
            # Add spacing before dropdown
            parts.append(Text())
            parts.append(self.dropdown.render())

        # Tip (if no dropdown and tip provided)
        elif self.tip and not self.active_trigger and not self.buffer:
            tip_text = Text()
            tip_text.append("  ")
            tip_text.append(self.tip, style=COLORS["tip"])
            parts.append(tip_text)

        return Group(*parts)

    def _accept_selection(self) -> bool:
        """Accept current dropdown selection. Returns True if handled directory navigation."""
        value = self.dropdown.selected_value
        if value is None:
            return False

        # Handle directory navigation for FileProvider
        if isinstance(value, str) and value.endswith('/'):
            provider = self._get_provider()
            if isinstance(provider, FileProvider):
                provider.enter(value)
                self.filter_text = ""
                self._update_dropdown()
                return True

        # Accept the selection
        self.buffer += str(value)
        self._exit_autocomplete()
        return False

    def _exit_autocomplete(self):
        """Exit autocomplete mode."""
        self.active_trigger = None
        self.filter_text = ""
        self.dropdown.clear()
        # Reset FileProvider context
        for provider in self.triggers.values():
            if isinstance(provider, FileProvider):
                provider.context = ""

    def run(self) -> str:
        """Run input and return entered text.

        fzf-style keybindings:
        - Enter: confirm selection (accepts first/selected match), or submit if no dropdown
        - Tab: reserved for future multi-select toggle
        - Up/Down: navigate (optional, typing to filter is primary)
        - Escape: cancel autocomplete
        """
        with Live(self._render(), console=self.console, refresh_per_second=20, auto_refresh=False) as live:
            while True:
                key = read_key()

                if key in ('\r', '\n'):  # Enter - confirm selection or submit
                    if self.active_trigger:
                        if not self.dropdown.is_empty:
                            # Accept current selection (first match if not navigated)
                            if self._accept_selection():
                                # Directory navigation - stay in autocomplete
                                live.update(self._render(), refresh=True)
                                continue
                            # File selected - exit autocomplete, continue typing
                            live.update(self._render(), refresh=True)
                        else:
                            # No matches - exit autocomplete mode
                            self._exit_autocomplete()
                            live.update(self._render(), refresh=True)
                    else:
                        # Not in autocomplete - submit input
                        return self.buffer

                elif key == '\t':  # Tab - reserved for multi-select toggle
                    # For now, same as Enter for single select
                    if self.active_trigger and not self.dropdown.is_empty:
                        if self._accept_selection():
                            live.update(self._render(), refresh=True)
                            continue
                        live.update(self._render(), refresh=True)

                elif key == 'esc':  # ESC - cancel autocomplete
                    if self.active_trigger:
                        # Remove trigger char from buffer
                        if self.buffer.endswith(self.active_trigger):
                            self.buffer = self.buffer[:-1]
                        self._exit_autocomplete()
                        live.update(self._render(), refresh=True)

                elif key in ('\x03', '\x04'):  # Ctrl+C/D
                    raise KeyboardInterrupt()

                elif key in ('\x7f', '\x08'):  # Backspace
                    if self.active_trigger:
                        if self.filter_text:
                            self.filter_text = self.filter_text[:-1]
                            self._update_dropdown()
                        else:
                            # Try to go back in FileProvider
                            provider = self._get_provider()
                            if isinstance(provider, FileProvider) and provider.context:
                                provider.back()
                                self._update_dropdown()
                            else:
                                # Exit autocomplete, remove trigger
                                if self.buffer.endswith(self.active_trigger):
                                    self.buffer = self.buffer[:-1]
                                self._exit_autocomplete()
                        live.update(self._render(), refresh=True)
                    elif self.buffer:
                        self.buffer = self.buffer[:-1]
                        live.update(self._render(), refresh=True)

                elif key == 'up':
                    if self.active_trigger:
                        self.dropdown.up()
                        live.update(self._render(), refresh=True)

                elif key == 'down':
                    if self.active_trigger:
                        self.dropdown.down()
                        live.update(self._render(), refresh=True)

                elif key in self.triggers:  # Trigger char
                    self.active_trigger = key
                    self.filter_text = ""
                    self.buffer += key
                    self._update_dropdown()
                    live.update(self._render(), refresh=True)

                elif key.isprintable():
                    if self.active_trigger:
                        self.filter_text += key
                        self._update_dropdown()
                    else:
                        self.buffer += key
                    live.update(self._render(), refresh=True)
