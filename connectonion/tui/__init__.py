"""
Purpose: Terminal UI components for interactive agent interfaces with powerline-style rendering
LLM-Note:
  Dependencies: imports from [input, dropdown, providers, keys, fuzzy, status_bar, divider, pick, footer] | imported by [useful_tools/__init__.py, useful_tools/terminal.py] | requires rich library
  Data flow: agent/CLI imports TUI components → components render to terminal via Rich → user interacts via keyboard → components return selected values
  State/Effects: manages terminal state during interaction | raw mode for keyboard input | restores terminal on exit
  Integration: exposes Input (text with autocomplete), Dropdown, FileProvider/StaticProvider (autocomplete sources), StatusBar/SimpleStatusBar/ProgressSegment, Divider, pick (single-select), Footer | keyboard handling via getch/read_key | fuzzy matching via fuzzy_match/highlight_match
  Performance: renders to terminal in real-time | fuzzy matching is O(n*m) | file provider reads filesystem
  Errors: KeyboardInterrupt handled for clean exit | terminal restoration on exception

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
from .pick import pick
from .footer import Footer

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
    "pick",
    "Footer",
]
