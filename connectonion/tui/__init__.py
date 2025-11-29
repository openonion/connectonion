"""
ConnectOnion TUI - Terminal UI components.

Powerline-style terminal components inspired by powerlevel10k.

Usage:
    from connectonion.tui import Input, FileProvider, StatusBar, Divider

    # Status bar with model/context/git info
    status = StatusBar([
        ("🤖", "co/gemini-2.5-pro", "magenta"),
        ("📊", "50%", "green"),
        ("", "main", "blue"),
    ])
    console.print(status.render())

    # Minimal input with @ file autocomplete
    text = Input(triggers={"@": FileProvider()}).run()

    # Divider line
    console.print(Divider().render())
"""

from .input import Input
from .dropdown import Dropdown, DropdownItem
from .providers import FileProvider, StaticProvider
from .keys import getch, read_key
from .fuzzy import fuzzy_match, highlight_match
from .status_bar import StatusBar, SimpleStatusBar, ProgressSegment
from .divider import Divider

__all__ = [
    "Input",
    "Dropdown",
    "DropdownItem",
    "FileProvider",
    "StaticProvider",
    "getch",
    "read_key",
    "fuzzy_match",
    "highlight_match",
    "StatusBar",
    "SimpleStatusBar",
    "ProgressSegment",
    "Divider",
]
