"""
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


def browse_files(start_path: str = ".") -> Union[str, None]:
    """Browse files and folders interactively.

    Args:
        start_path: Starting directory (default: current directory)

    Returns:
        Selected file/folder path or None if cancelled

    Example:
        path = browse_files()
        # User navigates folders with arrow keys + Enter
        # Press Enter on file to select
        # Returns: "src/agent.py"
    """
    from pathlib import Path

    console = Console()
    current_path = Path(start_path).resolve()

    while True:
        # Get files and folders
        try:
            items = list(current_path.iterdir())
        except PermissionError:
            console.print(f"[red]Permission denied: {current_path}[/]")
            return None

        # Separate folders and files
        folders = sorted([f for f in items if f.is_dir() and not f.name.startswith('.')], key=lambda x: x.name)
        files = sorted([f for f in items if f.is_file() and not f.name.startswith('.')], key=lambda x: x.name)

        # Build options
        options = []
        all_items = []

        # Add parent directory if not at root
        if current_path.parent != current_path:
            options.append("📁 ../")
            all_items.append(("parent", current_path.parent))

        # Add folders
        for folder in folders:
            options.append(f"📁 {folder.name}/")
            all_items.append(("folder", folder))

        # Add files
        for file in files:
            options.append(f"📄 {file.name}")
            all_items.append(("file", file))

        if not options:
            console.print("[yellow]Empty directory[/]")
            return None

        # Show current path
        console.print(f"\n[cyan]Current:[/] {current_path}")
        choice = pick("Select file (or folder to navigate):", options, console=console)

        # Find selected item
        idx = options.index(choice)
        item_type, item_path = all_items[idx]

        if item_type in ("parent", "folder"):
            # Navigate to folder
            current_path = item_path
        else:
            # File selected - return relative path
            try:
                return str(item_path.relative_to(Path.cwd()))
            except ValueError:
                return str(item_path)


def input_with_at(prompt: str = "> ") -> str:
    """Get user input with @ autocomplete for file paths.

    When user types @, shows inline file autocomplete. Type to filter, arrows to navigate.

    Args:
        prompt: Input prompt to display

    Returns:
        User input with file paths inserted

    Example:
        cmd = input_with_at("> ")
        # User types: "edit "
        # User types: "@"
        # Inline autocomplete appears below (doesn't block input)
        # User types: "age" - filters to "agent.py"
        # Tab/Enter to accept, ESC to cancel
    """
    from pathlib import Path

    console = Console()
    if prompt:
        console.print(prompt, end="")

    buffer = ""
    autocomplete_active = False
    autocomplete_filter = ""
    autocomplete_selected = 0
    autocomplete_items = []

    def get_file_suggestions(filter_text: str, current_path: Path = None):
        """Get filtered file suggestions from directory."""
        if current_path is None:
            current_path = Path.cwd()

        try:
            items = list(current_path.iterdir())
            # Filter hidden files
            items = [f for f in items if not f.name.startswith('.')]

            # Apply text filter
            if filter_text:
                items = [f for f in items if filter_text.lower() in f.name.lower()]

            # Sort: folders first, then by name, limit to 5
            items = sorted(items, key=lambda x: (not x.is_dir(), x.name.lower()))[:5]
            return items
        except (PermissionError, OSError):
            return []

    def render_autocomplete():
        """Render autocomplete dropdown below cursor."""
        if not autocomplete_items:
            sys.stdout.write("\n[dim]No matches[/]\033[1A")
            sys.stdout.flush()
            return

        # Print each suggestion on new line
        for i, item in enumerate(autocomplete_items):
            sys.stdout.write("\n")
            if i == autocomplete_selected:
                icon = "📁" if item.is_dir() else "📄"
                sys.stdout.write(f"\033[1;36m❯ {icon} {item.name}\033[0m")
            else:
                icon = "📁" if item.is_dir() else "📄"
                sys.stdout.write(f"\033[2m  {icon} {item.name}\033[0m")

        # Move cursor back to input line
        sys.stdout.write(f"\033[{len(autocomplete_items)}A")
        sys.stdout.flush()

    def clear_autocomplete():
        """Clear autocomplete dropdown."""
        if autocomplete_items:
            # Move down, clear lines, move back up
            for i in range(len(autocomplete_items)):
                sys.stdout.write("\n\033[K")
            sys.stdout.write(f"\033[{len(autocomplete_items)}A")
            sys.stdout.flush()

    while True:
        ch = _getch()

        # Autocomplete mode
        if autocomplete_active:
            if ch == '\x1b':  # ESC - cancel autocomplete
                clear_autocomplete()
                # Keep @ and filter in buffer
                buffer = buffer + '@' + autocomplete_filter
                # Redraw line cleanly
                sys.stdout.write('\r\033[K')
                sys.stdout.write(prompt + buffer)
                sys.stdout.flush()
                autocomplete_active = False
                autocomplete_filter = ""
                autocomplete_items = []

            elif ch in ('\t', '\r', '\n'):  # Tab/Enter - accept selection
                clear_autocomplete()
                if autocomplete_items and autocomplete_selected < len(autocomplete_items):
                    selected_item = autocomplete_items[autocomplete_selected]
                    selected_name = selected_item.name
                    if selected_item.is_dir():
                        selected_name += "/"

                    # Replace @filter with selected file
                    buffer = buffer + selected_name
                else:
                    # No selection, keep @ and filter as-is
                    buffer = buffer + '@' + autocomplete_filter

                # Redraw line cleanly
                sys.stdout.write('\r\033[K')
                sys.stdout.write(prompt + buffer)
                sys.stdout.flush()

                autocomplete_active = False
                autocomplete_filter = ""
                autocomplete_items = []

            elif ch == 'up':
                if autocomplete_items:
                    clear_autocomplete()
                    autocomplete_selected = (autocomplete_selected - 1) % len(autocomplete_items)
                    render_autocomplete()

            elif ch == 'down':
                if autocomplete_items:
                    clear_autocomplete()
                    autocomplete_selected = (autocomplete_selected + 1) % len(autocomplete_items)
                    render_autocomplete()

            elif ch in ('\x7f', '\x08'):  # Backspace
                if autocomplete_filter:
                    autocomplete_filter = autocomplete_filter[:-1]
                    # Redraw line cleanly
                    clear_autocomplete()
                    sys.stdout.write('\r\033[K')
                    full_text = buffer + '@' + autocomplete_filter
                    sys.stdout.write(prompt + full_text)
                    sys.stdout.flush()
                    # Update suggestions
                    autocomplete_items = get_file_suggestions(autocomplete_filter)
                    autocomplete_selected = 0
                    render_autocomplete()
                else:
                    # Cancel autocomplete if filter is empty, remove @ too
                    clear_autocomplete()
                    sys.stdout.write('\r\033[K')
                    sys.stdout.write(prompt + buffer)
                    sys.stdout.flush()
                    autocomplete_active = False
                    autocomplete_items = []

            elif ch.isprintable():
                # Add to filter
                autocomplete_filter += ch
                # Redraw the input line cleanly
                clear_autocomplete()
                # Move to start of line, clear line, rewrite everything
                sys.stdout.write('\r\033[K')
                full_text = buffer + '@' + autocomplete_filter
                sys.stdout.write(prompt + full_text)
                sys.stdout.flush()
                # Update suggestions
                autocomplete_items = get_file_suggestions(autocomplete_filter)
                autocomplete_selected = 0
                render_autocomplete()

        # Normal input mode
        else:
            if ch in ('\r', '\n'):  # Enter - submit
                print()
                return buffer

            elif ch in ('\x03', '\x04'):  # Ctrl+C/D - abort
                print()
                raise KeyboardInterrupt()

            elif ch in ('\x7f', '\x08'):  # Backspace
                if buffer:
                    buffer = buffer[:-1]
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()

            elif ch == '@':  # Start autocomplete
                buffer += '@'
                sys.stdout.write('@')
                sys.stdout.flush()
                autocomplete_active = True
                autocomplete_filter = ""
                autocomplete_items = get_file_suggestions("")
                autocomplete_selected = 0
                render_autocomplete()

            elif ch.isprintable():
                buffer += ch
                sys.stdout.write(ch)
                sys.stdout.flush()

            # Ignore other keys
            else:
                pass


if __name__ == "__main__":
    print("=== pick / yes_no Demo ===\n")

    fruit = pick("Pick a fruit", ["Apple", "Banana", "Cherry"])
    print(f"\nYou picked: {fruit}\n")

    action = pick("What to do?", {"c": "Continue", "r": "Retry", "q": "Quit"})
    print(f"\nYou chose: {action}\n")

    ok = yes_no("Are you sure?")
    print(f"\nConfirmed: {ok}\n")

    print("\n=== browse_files Demo ===\n")
    path = browse_files()
    print(f"\nSelected: {path}\n")

    print("\n=== input_with_at Demo ===\n")
    cmd = input_with_at("Command: ")
    print(f"\nFinal input: {cmd}")
