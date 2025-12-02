"""
Purpose: Single-select menu component with keyboard navigation for terminal-based option selection
LLM-Note:
  Dependencies: imports from [sys, rich.console, rich.live, rich.text, .keys] | imported by [tui/__init__.py, useful_tools/__init__.py] | used in CLI menus and agent tool confirmations
  Data flow: caller invokes pick(title, options, other) → renders menu with Rich Live → reads keyboard via read_key() → up/down arrows move selection → Enter confirms → returns selected label string | if other=True and "Other..." selected, prompts for custom text input
  State/Effects: uses Rich Live for in-place rendering | manages cursor position state | reads raw keyboard input | no file I/O
  Integration: exposes pick(title, options, other, console) → str | options can be strings or (label, description) tuples | optional "Other..." for custom input | returns selected label or custom text
  Performance: O(n) options rendering | single keystroke per action | real-time re-render on selection change
  Errors: KeyboardInterrupt returns None or empty string | terminal restored on exit

Usage:
    from connectonion.tui import pick

    # Simple list selection
    choice = pick("Pick a color", ["Red", "Green", "Blue"])

    # With descriptions
    choice = pick("Send email?", [
        ("Yes, send it", "Send immediately"),
        ("Auto approve", "Skip for this recipient"),
    ])

    # With "Other" option for custom input
    choice = pick("Continue?", ["Yes", "No"], other=True)
"""

import sys
from rich.console import Console
from rich.live import Live
from rich.text import Text
from .keys import read_key


def pick(title: str, options: list, other: bool = False, console: Console = None) -> str:
    """Single-select menu with keyboard navigation.

    Args:
        title: Question to display
        options: List of strings or (label, description) tuples
        other: Add "Other..." option for custom text input
        console: Optional Rich console

    Returns:
        Selected option label, or custom text if "Other" chosen
    """
    console = console or Console()

    # Normalize options to (label, description) tuples
    items = []
    for opt in options:
        if isinstance(opt, str):
            items.append((opt, ""))
        else:
            items.append((opt[0], opt[1] if len(opt) > 1 else ""))
    if other:
        items.append(("Other...", ""))

    selected = 0
    total = len(items)
    lines = total + 4  # title + blank + options + blank + footer

    def render() -> Text:
        out = Text()
        out.append(f"{title}\n\n", style="bold")
        for i, (label, desc) in enumerate(items):
            if i == selected:
                out.append(f"  ❯ {i+1}  {label}", style="bold cyan")
            else:
                out.append(f"    {i+1}  ", style="dim cyan")
                out.append(label, style="dim")
            if desc:
                out.append(f"  {desc}", style="dim")
            out.append("\n")
        # Footer with key hints
        out.append("\n")
        out.append("↑↓", style="cyan")
        out.append(" navigate  ", style="dim")
        out.append("1-9", style="cyan")
        out.append(" jump  ", style="dim")
        out.append("Enter", style="cyan")
        out.append(" select", style="dim")
        return out

    def show_result(text: str):
        sys.stdout.write(f"\033[{lines}A\033[J")  # Clear menu
        result = Text()
        result.append(f"{title} ", style="bold")
        result.append("✓ ", style="green")
        result.append(text, style="dim")
        console.print(result)

    def get_other_input() -> str:
        sys.stdout.write(f"\033[{lines}A\033[J")  # Clear menu
        console.print(f"[bold]{title}[/]")
        return input("  → ")

    def handle_select(idx: int) -> str:
        if other and idx == total - 1:
            return get_other_input()
        label = items[idx][0]
        show_result(label)
        return label

    # Hide cursor and run
    print("\033[?25l", end="", flush=True)
    try:
        with Live(render(), console=console, auto_refresh=False) as live:
            while True:
                key = read_key()

                if key == 'up':
                    selected = (selected - 1) % total
                    live.update(render(), refresh=True)
                elif key == 'down':
                    selected = (selected + 1) % total
                    live.update(render(), refresh=True)
                elif key in ('\r', '\n'):
                    live.stop()
                    print("\033[?25h", end="", flush=True)
                    return handle_select(selected)
                elif key.isdigit() and 0 < int(key) <= total:
                    live.stop()
                    print("\033[?25h", end="", flush=True)
                    return handle_select(int(key) - 1)
                elif key == '\x03':
                    raise KeyboardInterrupt()
                elif key == '\x04':
                    raise EOFError()
    finally:
        print("\033[?25h", end="", flush=True)
