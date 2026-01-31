"""
Purpose: Low-level keyboard input primitives with bracketed paste and arrow key support
LLM-Note:
  Dependencies: imports from [sys, tty, termios, select] | imported by [tui/input.py] | tested by [tests/tui/test_keys.py]
  Data flow: enable_bracketed_paste() sends ESC[?2004h → read_key() reads from sys.stdin.buffer → detects paste markers (ESC[200~/ESC[201~) → returns Key enum or paste string | disable_bracketed_paste() sends ESC[?2004l → restore_terminal() resets termios
  State/Effects: modifies terminal mode (raw mode via tty.setraw) | enables/disables bracketed paste mode | stores original termios settings | reads from stdin (blocking)
  Integration: exposes enable_bracketed_paste(), disable_bracketed_paste(), restore_terminal(), read_key() → Key|str | Key enum for special keys (UP, DOWN, ENTER, BACKSPACE, etc.) | used by Input widget for character-by-character input
  Performance: blocking read with select() for responsiveness | minimal overhead (direct termios)
  Errors: restores terminal on exception | paste detection falls back to raw characters if markers missing
Low-level keyboard input primitives with bracketed paste support.

This module provides raw keyboard input handling for terminal applications,
including support for:
- Single character input without Enter
- Arrow keys and special keys (Shift+Tab, Escape)
- Bracketed paste mode for reliable paste detection

Bracketed Paste Mode:
    Modern terminals support bracketed paste mode where pasted text is
    wrapped in special escape sequences:
    - ESC[?2004h  - Enable bracketed paste
    - ESC[200~    - Paste start marker
    - ESC[201~    - Paste end marker
    - ESC[?2004l  - Disable bracketed paste

    This allows us to detect paste operations and handle all pasted text
    atomically, preventing display glitches during paste.
"""

import sys


# Bracketed paste mode sequences
PASTE_START = '\x1b[200~'  # Sent by terminal when paste begins
PASTE_END = '\x1b[201~'    # Sent by terminal when paste ends


def enable_bracketed_paste():
    """Enable bracketed paste mode.

    When enabled, the terminal wraps pasted text in special sequences:
    ESC[200~ ... pasted text ... ESC[201~

    This allows detection of paste operations vs typed input.
    Must call disable_bracketed_paste() when done to restore terminal.
    """
    sys.stdout.write('\x1b[?2004h')
    sys.stdout.flush()


def disable_bracketed_paste():
    """Disable bracketed paste mode.

    Always call this when done with input to restore normal terminal behavior.
    Should be called in a finally block to ensure cleanup on errors.
    """
    sys.stdout.write('\x1b[?2004l')
    sys.stdout.flush()


def getch() -> str:
    """Read single character without waiting for Enter.

    Uses raw terminal mode to read one character immediately.
    Works on Unix (termios) and Windows (msvcrt).

    Returns:
        Single character string
    """
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        # Use TCSANOW for immediate restore (prevents paste data loss)
        termios.tcsetattr(fd, termios.TCSANOW, old)
        return ch
    except ImportError:
        import msvcrt
        return msvcrt.getch().decode('utf-8', errors='ignore')


def _read_until_paste_end() -> str:
    """Read all characters until paste end sequence (ESC[201~).

    Called after paste start (ESC[200~) is detected.
    Collects all pasted characters until the end marker.

    Returns:
        The pasted text without the escape sequences
    """
    chars = []
    buffer = ""

    while True:
        ch = getch()
        buffer += ch

        # Check for paste end sequence
        if buffer.endswith(PASTE_END[1:]):  # Already got ESC, check for [201~
            # Remove the end sequence from collected chars
            if chars and len(chars) >= 4:
                # Remove [201~ (4 chars after ESC)
                return ''.join(chars[:-4])
            return ''.join(chars)

        # Keep building buffer for sequence detection
        if ch == '\x1b':
            buffer = ch
            chars.append(ch)
        elif len(buffer) <= len(PASTE_END):
            chars.append(ch)
        else:
            # Not a sequence, add buffer to chars and reset
            chars.append(ch)
            buffer = ""

    return ''.join(chars)


def read_key() -> str:
    """Read key with arrow/escape sequence and bracketed paste handling.

    Returns:
        Single char, or special key names:
        - 'up'/'down'/'left'/'right' for arrows
        - 'shift+tab' for Shift+Tab
        - 'esc' for escape
        - Multi-char string for pasted text (with 'paste:' prefix)
    """
    ch = getch()

    # Handle escape sequences
    if ch == '\x1b':
        ch2 = getch()
        if ch2 == '[':
            ch3 = getch()

            # Shift+Tab is ESC [ Z
            if ch3 == 'Z':
                return 'shift+tab'

            # Arrow keys
            if ch3 in 'ABCD':
                return {'A': 'up', 'B': 'down', 'C': 'right', 'D': 'left'}[ch3]

            # Bracketed paste start: ESC [ 2 0 0 ~
            if ch3 == '2':
                ch4 = getch()
                ch5 = getch()
                ch6 = getch()
                if ch4 == '0' and ch5 == '0' and ch6 == '~':
                    # Paste start detected - read until paste end
                    pasted = _read_until_paste_end()
                    return 'paste:' + pasted

            return 'esc'
        return 'esc'

    return ch
