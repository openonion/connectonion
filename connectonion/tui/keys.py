"""Low-level keyboard input primitives."""

import sys


def getch() -> str:
    """Read single character without waiting for Enter."""
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return ch
    except ImportError:
        import msvcrt
        return msvcrt.getch().decode('utf-8', errors='ignore')


def read_key() -> str:
    """Read key with arrow/escape sequence handling.

    Returns:
        Single char, or 'up'/'down'/'left'/'right' for arrows, 'esc' for escape
    """
    ch = getch()
    if ch == '\x1b':
        ch2 = getch()
        if ch2 == '[':
            ch3 = getch()
            return {'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left'}.get(ch3, 'esc')
        return 'esc'
    return ch
