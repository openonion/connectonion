"""
Purpose: CLI input utilities for single keypress selection, file browsing, and @ autocomplete
LLM-Note:
  Dependencies: imports from [sys, typing, rich.console, termios/tty (Unix), msvcrt (Windows)] | imported by [useful_tools/__init__.py, tui/__init__.py] | tested by [tests/unit/test_terminal.py]
  Data flow: pick(prompt, options) → displays numbered options → _getch()/_read_key() waits for keypress → returns selected option text or key | browse_files() → displays directory listing with rich.live → arrow keys navigate → returns selected file path | input_with_at() → standard input with @ triggering file browser
  State/Effects: blocks on user input | uses raw terminal mode via termios/tty (Unix) or msvcrt (Windows) | no persistent state | no network I/O
  Integration: exposes pick(), yes_no(), browse_files(), input_with_at(), autocomplete() | pick() accepts list (numbered) or dict (custom keys) | used for human-in-the-loop agent tools
  Performance: instant response after keypress | no computation overhead | blocks on user input
  Errors: returns None if user cancels | handles keyboard interrupts gracefully | no exceptions raised

CLI input utilities - single keypress select, file browser, and @ autocomplete.

Usage:
    from connectonion import pick, yes_no, browse_files, input_with_at

    # Recommended: Numbered options (1, 2, 3) for agent interactions
    choice = pick("Apply this command?", [
        "Yes, apply",
        "Yes for same command",
        "No, I'll tell agent how to do it"
    ])
    # Press 1 → "Yes, apply", 2 → "Yes for same command", 3 → "No, I'll tell agent how to do it"
    # Or use arrow keys + Enter

    # Pick from list (returns option text)
    choice = pick("Pick a color", ["Red", "Green", "Blue"])
    # Press 1 → "Red", 2 → "Green", 3 → "Blue"

    # Pick with custom keys (returns key)
    choice = pick("Continue?", {
        "y": "Yes, continue",
        "n": "No, cancel",
    })
    # Press y → "y", n → "n"

    # Yes/No confirmation (simple binary choice)
    ok = yes_no("Are you sure?")
    # Press y → True, n → False

    # Browse files and folders
    path = browse_files()
    # Navigate with arrow keys, Enter on folders to open, Enter on files to select
    # Returns: "src/agent.py"

    # Input with @ autocomplete
    cmd = input_with_at("> ")
    # User types: "edit @"
    # File browser opens automatically
    # Returns: "edit src/agent.py"
"""

import sys
from typing import Union

from rich.console import Console


def _getch():
    """Read a single character from stdin without waiting for Enter."""
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch
    except ImportError:
        import msvcrt
        return msvcrt.getch().decode('utf-8', errors='ignore')


def _read_key():
    """Read a key, handling arrow key escape sequences."""
    ch = _getch()
    if ch == '\x1b':  # Escape sequence
        ch2 = _getch()
        if ch2 == '[':
            ch3 = _getch()
            if ch3 == 'A':
                return 'up'
            elif ch3 == 'B':
                return 'down'
            elif ch3 == 'C':
                return 'right'
            elif ch3 == 'D':
                return 'left'
    return ch


def pick(
    title: str,
    options: Union[list, dict],
    console: Console = None,
) -> str:
    """Pick one option - arrow keys or number/letter selection.

    Args:
        title: The question/title to display
        options: Either a list (numbered 1,2,3...) or dict (custom keys)
        console: Optional Rich console instance

    Returns:
        If list: the selected option text
        If dict: the selected key

    Example:
        choice = pick("Pick one", ["Apple", "Banana"])
        # Press 2 or arrow down + Enter → "Banana"

        action = pick("Continue?", {"y": "Yes", "n": "No"})
        # Press y → "y"
    """
    if console is None:
        console = Console()

    # Build key map and items list
    if isinstance(options, list):
        key_map = {}
        items = []
        for i, opt in enumerate(options, 1):
            key = str(i)
            key_map[key] = opt
            items.append((key, opt))
    else:
        key_map = options
        items = list(options.items())

    selected = 0  # Current selection index

    def render(first=False):
        """Render the menu with current selection highlighted."""
        if not first:
            # Move cursor up to redraw
            lines_to_clear = len(items) + (2 if title else 1)
            sys.stdout.write(f"\033[{lines_to_clear}A")  # Move up
            sys.stdout.write("\033[J")  # Clear from cursor to end

        if title:
            console.print(f"[bold]{title}[/]")
        console.print()

        for i, (key, desc) in enumerate(items):
            if i == selected:
                console.print(f"  [bold cyan]❯[/] [bold cyan]{key}[/]  [bold]{desc}[/]")
            else:
                console.print(f"    [dim]{key}[/]  {desc}")

    # Initial render
    render(first=True)

    # Hide cursor
    print("\033[?25l", end="", flush=True)

    try:
        while True:
            key = _read_key()

            if key == 'up':
                selected = (selected - 1) % len(items)
                render(first=False)
            elif key == 'down':
                selected = (selected + 1) % len(items)
                render(first=False)
            elif key in ('\r', '\n'):  # Enter
                print("\033[?25h", end="", flush=True)
                chosen_key = items[selected][0]
                if isinstance(options, list):
                    return key_map[chosen_key]
                return chosen_key
            elif key in key_map:
                print("\033[?25h", end="", flush=True)
                if isinstance(options, list):
                    return key_map[key]
                return key
            elif key in ("\x03", "\x04"):  # Ctrl+C, Ctrl+D
                print("\033[?25h", end="", flush=True)
                raise KeyboardInterrupt()
    finally:
        print("\033[?25h", end="", flush=True)


def yes_no(
    message: str,
    default: bool = True,
    console: Console = None,
) -> bool:
    """Yes/No confirmation - single keypress.

    Args:
        message: The question to ask
        default: Default value if Enter is pressed
        console: Optional Rich console instance

    Returns:
        True for yes, False for no
    """
    if console is None:
        console = Console()

    yes_key = "Y" if default else "y"
    no_key = "n" if default else "N"

    console.print()
    console.print(f"[bold]{message}[/] [dim]({yes_key}/{no_key})[/] ", end="")

    while True:
        ch = _getch().lower()
        if ch == "y":
            console.print("yes")
            return True
        elif ch == "n":
            console.print("no")
            return False
        elif ch in ("\r", "\n"):  # Enter
            console.print("yes" if default else "no")
            return default
        elif ch in ("\x03", "\x04"):  # Ctrl+C, Ctrl+D
            raise KeyboardInterrupt()


def autocomplete(suggestions: list, max_visible: int = 5) -> Union[str, None]:
    """Show inline autocomplete dropdown with arrow key navigation.

    Pure UI component - displays suggestions and handles selection.
    Does NOT handle filtering or search logic - that's the caller's job.

    Args:
        suggestions: List of strings to display
        max_visible: Maximum suggestions to show (default: 5)

    Returns:
        Selected string or None if cancelled (ESC pressed)

    Example:
        from connectonion import autocomplete

        files = ["agent.py", "main.py", "utils.py"]
        selected = autocomplete(files)
        if selected:
            print(f"Selected: {selected}")
    """
    from rich.live import Live
    from rich.table import Table

    if not suggestions:
        return None

    # Limit to max visible
    suggestions = suggestions[:max_visible]
    selected = 0

    def create_table():
        """Create table with current selection highlighted."""
        table = Table(show_header=False, box=None, padding=(0, 1), show_edge=False)
        for i, item in enumerate(suggestions):
            if i == selected:
                table.add_row(f"[cyan]❯ {item}[/]")
            else:
                table.add_row(f"[dim]  {item}[/]")
        return table

    # Show live display with keyboard navigation
    with Live(create_table(), refresh_per_second=10, auto_refresh=False) as live:
        while True:
            key = _read_key()

            if key == '\x1b':  # ESC - cancel
                return None

            elif key in ('\r', '\n', '\t'):  # Enter/Tab - accept
                return suggestions[selected]

            elif key == 'up':
                selected = (selected - 1) % len(suggestions)
                live.update(create_table(), refresh=True)

            elif key == 'down':
                selected = (selected + 1) % len(suggestions)
                live.update(create_table(), refresh=True)


