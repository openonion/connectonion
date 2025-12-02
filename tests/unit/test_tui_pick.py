"""Unit tests for connectonion/tui/pick.py

Tests cover:
- Option normalization logic
- Render function behavior
- Basic functionality

Note: Since pick() is an interactive TUI component that reads keyboard input
and uses Rich Live, we test with mocked terminal interaction.
"""

import pytest
import importlib
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

# Import the module directly to avoid __init__.py shadowing
pick_module = importlib.import_module('connectonion.tui.pick')
pick = pick_module.pick


class TestPickFunctionality:
    """Tests for pick function with mocked terminal."""

    def test_pick_returns_first_option_on_enter(self):
        """Test selecting first option with Enter."""
        # Mock read_key to return Enter immediately
        with patch.object(pick_module, 'read_key', return_value='\r'):
            with patch('sys.stdout.write'):
                with patch.object(pick_module, 'Live') as mock_live:
                    mock_live.return_value.__enter__ = Mock(return_value=MagicMock())
                    mock_live.return_value.__exit__ = Mock(return_value=False)

                    result = pick("Title", ["First", "Second", "Third"])

        assert result == "First"

    def test_pick_returns_option_by_number_key(self):
        """Test selecting option with number key."""
        with patch.object(pick_module, 'read_key', return_value='2'):
            with patch('sys.stdout.write'):
                with patch.object(pick_module, 'Live') as mock_live:
                    mock_live.return_value.__enter__ = Mock(return_value=MagicMock())
                    mock_live.return_value.__exit__ = Mock(return_value=False)

                    result = pick("Title", ["First", "Second", "Third"])

        assert result == "Second"

    def test_pick_with_tuple_options(self):
        """Test that tuple options return the label."""
        with patch.object(pick_module, 'read_key', return_value='\r'):
            with patch('sys.stdout.write'):
                with patch.object(pick_module, 'Live') as mock_live:
                    mock_live.return_value.__enter__ = Mock(return_value=MagicMock())
                    mock_live.return_value.__exit__ = Mock(return_value=False)

                    result = pick("Title", [
                        ("Label1", "Description1"),
                        ("Label2", "Description2"),
                    ])

        assert result == "Label1"

    def test_pick_navigation_down(self):
        """Test navigating down then selecting."""
        call_count = [0]
        def mock_read_key():
            call_count[0] += 1
            if call_count[0] == 1:
                return 'down'
            return '\r'

        with patch.object(pick_module, 'read_key', side_effect=mock_read_key):
            with patch('sys.stdout.write'):
                with patch.object(pick_module, 'Live') as mock_live:
                    mock_instance = MagicMock()
                    mock_live.return_value.__enter__ = Mock(return_value=mock_instance)
                    mock_live.return_value.__exit__ = Mock(return_value=False)

                    result = pick("Title", ["First", "Second", "Third"])

        assert result == "Second"

    def test_pick_navigation_up_wraps(self):
        """Test that navigating up from first wraps to last."""
        call_count = [0]
        def mock_read_key():
            call_count[0] += 1
            if call_count[0] == 1:
                return 'up'
            return '\r'

        with patch.object(pick_module, 'read_key', side_effect=mock_read_key):
            with patch('sys.stdout.write'):
                with patch.object(pick_module, 'Live') as mock_live:
                    mock_instance = MagicMock()
                    mock_live.return_value.__enter__ = Mock(return_value=mock_instance)
                    mock_live.return_value.__exit__ = Mock(return_value=False)

                    result = pick("Title", ["First", "Second", "Third"])

        assert result == "Third"

    def test_pick_keyboard_interrupt(self):
        """Test that Ctrl+C raises KeyboardInterrupt."""
        with patch.object(pick_module, 'read_key', return_value='\x03'):
            with patch('sys.stdout.write'):
                with patch.object(pick_module, 'Live') as mock_live:
                    mock_live.return_value.__enter__ = Mock(return_value=MagicMock())
                    mock_live.return_value.__exit__ = Mock(return_value=False)

                    with pytest.raises(KeyboardInterrupt):
                        pick("Title", ["First", "Second"])

    def test_pick_with_other_option(self):
        """Test that other=True adds 'Other...' option."""
        # Select the 3rd option (which is "Other..." when other=True)
        with patch.object(pick_module, 'read_key', return_value='3'):
            with patch('sys.stdout.write'):
                with patch('builtins.input', return_value='Custom value'):
                    with patch.object(pick_module, 'Live') as mock_live:
                        mock_live.return_value.__enter__ = Mock(return_value=MagicMock())
                        mock_live.return_value.__exit__ = Mock(return_value=False)

                        result = pick("Title", ["First", "Second"], other=True)

        assert result == "Custom value"

    def test_pick_invalid_number_ignored(self):
        """Test that invalid number keys are ignored."""
        call_count = [0]
        def mock_read_key():
            call_count[0] += 1
            if call_count[0] == 1:
                return '9'  # Invalid for 2 options
            return '\r'

        with patch.object(pick_module, 'read_key', side_effect=mock_read_key):
            with patch('sys.stdout.write'):
                with patch.object(pick_module, 'Live') as mock_live:
                    mock_instance = MagicMock()
                    mock_live.return_value.__enter__ = Mock(return_value=mock_instance)
                    mock_live.return_value.__exit__ = Mock(return_value=False)

                    result = pick("Title", ["First", "Second"])

        # Should still be on first option after invalid key
        assert result == "First"


class TestPickImport:
    """Tests for pick module import."""

    def test_pick_can_be_imported(self):
        """Test that pick can be imported from tui."""
        from connectonion.tui import pick as pick_func
        assert callable(pick_func)

    def test_pick_module_has_read_key(self):
        """Test that pick module has read_key dependency."""
        assert hasattr(pick_module, 'read_key')
        assert callable(pick_module.read_key)
