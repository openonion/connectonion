"""Unit tests for connectonion/useful_tools/terminal.py

Tests cover:
- pick: option selection (mocked stdin)
- yes_no: boolean confirmation (mocked stdin)
- autocomplete: dropdown selection (mocked stdin)
- _getch and _read_key: key reading utilities

Note: These tests mock stdin since actual TTY interaction cannot be tested in pytest.
"""

import pytest
import sys
from unittest.mock import patch, Mock, MagicMock
from io import StringIO

from connectonion.useful_tools.terminal import pick, yes_no, autocomplete, _getch, _read_key


class TestGetch:
    """Tests for _getch function."""

    def test_getch_imports_termios(self):
        """Test that _getch tries to import termios on Unix."""
        # We can't easily test _getch without a real TTY
        # Just verify the function exists and is callable
        assert callable(_getch)


class TestReadKey:
    """Tests for _read_key function."""

    @patch('connectonion.useful_tools.terminal._getch')
    def test_read_key_regular_char(self, mock_getch):
        """Test reading a regular character."""
        mock_getch.return_value = 'x'

        result = _read_key()

        assert result == 'x'

    @patch('connectonion.useful_tools.terminal._getch')
    def test_read_key_arrow_up(self, mock_getch):
        """Test reading arrow up key."""
        mock_getch.side_effect = ['\x1b', '[', 'A']

        result = _read_key()

        assert result == 'up'

    @patch('connectonion.useful_tools.terminal._getch')
    def test_read_key_arrow_down(self, mock_getch):
        """Test reading arrow down key."""
        mock_getch.side_effect = ['\x1b', '[', 'B']

        result = _read_key()

        assert result == 'down'

    @patch('connectonion.useful_tools.terminal._getch')
    def test_read_key_arrow_right(self, mock_getch):
        """Test reading arrow right key."""
        mock_getch.side_effect = ['\x1b', '[', 'C']

        result = _read_key()

        assert result == 'right'

    @patch('connectonion.useful_tools.terminal._getch')
    def test_read_key_arrow_left(self, mock_getch):
        """Test reading arrow left key."""
        mock_getch.side_effect = ['\x1b', '[', 'D']

        result = _read_key()

        assert result == 'left'


class TestPick:
    """Tests for pick function."""

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('sys.stdout', new_callable=StringIO)
    def test_pick_list_number_selection(self, mock_stdout, mock_read_key):
        """Test selecting by number from list."""
        mock_read_key.return_value = '2'
        mock_console = Mock()

        result = pick("Choose:", ["Apple", "Banana", "Cherry"], console=mock_console)

        assert result == "Banana"

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('sys.stdout', new_callable=StringIO)
    def test_pick_list_enter_selection(self, mock_stdout, mock_read_key):
        """Test selecting with Enter key (first item is default)."""
        mock_read_key.return_value = '\r'
        mock_console = Mock()

        result = pick("Choose:", ["Apple", "Banana"], console=mock_console)

        assert result == "Apple"  # First item selected

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('sys.stdout', new_callable=StringIO)
    def test_pick_list_arrow_and_enter(self, mock_stdout, mock_read_key):
        """Test selecting with arrow keys then Enter."""
        mock_read_key.side_effect = ['down', 'down', '\r']
        mock_console = Mock()

        result = pick("Choose:", ["A", "B", "C"], console=mock_console)

        assert result == "C"  # Third item after two downs

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('sys.stdout', new_callable=StringIO)
    def test_pick_dict_key_selection(self, mock_stdout, mock_read_key):
        """Test selecting from dict by key."""
        mock_read_key.return_value = 'n'
        mock_console = Mock()

        result = pick("Continue?", {"y": "Yes", "n": "No"}, console=mock_console)

        assert result == "n"

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('sys.stdout', new_callable=StringIO)
    def test_pick_keyboard_interrupt(self, mock_stdout, mock_read_key):
        """Test Ctrl+C raises KeyboardInterrupt."""
        mock_read_key.return_value = '\x03'  # Ctrl+C
        mock_console = Mock()

        with pytest.raises(KeyboardInterrupt):
            pick("Choose:", ["A", "B"], console=mock_console)


class TestYesNo:
    """Tests for yes_no function."""

    @patch('connectonion.useful_tools.terminal._getch')
    def test_yes_no_returns_true_for_y(self, mock_getch):
        """Test yes_no returns True for 'y'."""
        mock_getch.return_value = 'y'
        mock_console = Mock()

        result = yes_no("Continue?", console=mock_console)

        assert result is True

    @patch('connectonion.useful_tools.terminal._getch')
    def test_yes_no_returns_false_for_n(self, mock_getch):
        """Test yes_no returns False for 'n'."""
        mock_getch.return_value = 'n'
        mock_console = Mock()

        result = yes_no("Continue?", console=mock_console)

        assert result is False

    @patch('connectonion.useful_tools.terminal._getch')
    def test_yes_no_enter_returns_default_true(self, mock_getch):
        """Test yes_no returns default (True) on Enter."""
        mock_getch.return_value = '\r'
        mock_console = Mock()

        result = yes_no("Continue?", default=True, console=mock_console)

        assert result is True

    @patch('connectonion.useful_tools.terminal._getch')
    def test_yes_no_enter_returns_default_false(self, mock_getch):
        """Test yes_no returns default (False) on Enter."""
        mock_getch.return_value = '\r'
        mock_console = Mock()

        result = yes_no("Continue?", default=False, console=mock_console)

        assert result is False

    @patch('connectonion.useful_tools.terminal._getch')
    def test_yes_no_case_insensitive(self, mock_getch):
        """Test yes_no is case insensitive."""
        mock_getch.return_value = 'Y'
        mock_console = Mock()

        result = yes_no("Continue?", console=mock_console)

        assert result is True

    @patch('connectonion.useful_tools.terminal._getch')
    def test_yes_no_keyboard_interrupt(self, mock_getch):
        """Test Ctrl+C raises KeyboardInterrupt."""
        mock_getch.return_value = '\x03'  # Ctrl+C
        mock_console = Mock()

        with pytest.raises(KeyboardInterrupt):
            yes_no("Continue?", console=mock_console)


class TestAutocomplete:
    """Tests for autocomplete function."""

    def test_autocomplete_empty_suggestions(self):
        """Test autocomplete with empty suggestions returns None."""
        result = autocomplete([])
        assert result is None

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('rich.live.Live')
    def test_autocomplete_enter_selects_first(self, mock_live, mock_read_key):
        """Test autocomplete selects first item on Enter."""
        mock_read_key.return_value = '\r'
        mock_live_instance = MagicMock()
        mock_live.return_value.__enter__ = Mock(return_value=mock_live_instance)
        mock_live.return_value.__exit__ = Mock(return_value=False)

        result = autocomplete(["apple", "banana", "cherry"])

        assert result == "apple"

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('rich.live.Live')
    def test_autocomplete_escape_cancels(self, mock_live, mock_read_key):
        """Test autocomplete returns None on ESC."""
        mock_read_key.return_value = '\x1b'
        mock_live_instance = MagicMock()
        mock_live.return_value.__enter__ = Mock(return_value=mock_live_instance)
        mock_live.return_value.__exit__ = Mock(return_value=False)

        result = autocomplete(["apple", "banana"])

        assert result is None

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('rich.live.Live')
    def test_autocomplete_arrow_down_and_enter(self, mock_live, mock_read_key):
        """Test autocomplete navigates down and selects."""
        mock_read_key.side_effect = ['down', '\r']
        mock_live_instance = MagicMock()
        mock_live.return_value.__enter__ = Mock(return_value=mock_live_instance)
        mock_live.return_value.__exit__ = Mock(return_value=False)

        result = autocomplete(["apple", "banana", "cherry"])

        assert result == "banana"

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('rich.live.Live')
    def test_autocomplete_tab_selects(self, mock_live, mock_read_key):
        """Test autocomplete selects on Tab."""
        mock_read_key.return_value = '\t'
        mock_live_instance = MagicMock()
        mock_live.return_value.__enter__ = Mock(return_value=mock_live_instance)
        mock_live.return_value.__exit__ = Mock(return_value=False)

        result = autocomplete(["apple", "banana"])

        assert result == "apple"

    @patch('connectonion.useful_tools.terminal._read_key')
    @patch('rich.live.Live')
    def test_autocomplete_max_visible(self, mock_live, mock_read_key):
        """Test autocomplete respects max_visible limit."""
        mock_read_key.return_value = '\r'
        mock_live_instance = MagicMock()
        mock_live.return_value.__enter__ = Mock(return_value=mock_live_instance)
        mock_live.return_value.__exit__ = Mock(return_value=False)

        # Pass more items than max_visible
        result = autocomplete(["a", "b", "c", "d", "e", "f", "g"], max_visible=3)

        # Should still work, just show first 3
        assert result == "a"
