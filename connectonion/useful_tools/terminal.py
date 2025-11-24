"""
CLI input utilities - single keypress select and confirm.

Usage:
    from connectonion import pick, yes_no

    # Pick from list (returns option text)
    choice = pick("Pick a color", ["Red", "Green", "Blue"])
    # Press 1 → "Red", 2 → "Green", 3 → "Blue"
    # Or use arrow keys + Enter

    # Pick with custom keys (returns key)
    choice = pick("Continue?", {
        "y": "Yes, continue",
        "n": "No, cancel",
    })
    # Press y → "y", n → "n"

    # Yes/No confirmation
    ok = yes_no("Are you sure?")
    # Press y → True, n → False
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


if __name__ == "__main__":
    print("=== pick / yes_no Demo ===\n")

    fruit = pick("Pick a fruit", ["Apple", "Banana", "Cherry"])
    print(f"\nYou picked: {fruit}\n")

    action = pick("What to do?", {"c": "Continue", "r": "Retry", "q": "Quit"})
    print(f"\nYou chose: {action}\n")

    ok = yes_no("Are you sure?")
    print(f"\nConfirmed: {ok}")
