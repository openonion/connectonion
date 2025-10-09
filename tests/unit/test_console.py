"""Unit tests for connectonion/console.py"""

import unittest
from unittest.mock import patch
import connectonion.console as console_mod


class TestConsole(unittest.TestCase):
    """Test console output functions."""

    @patch('connectonion.console._rich_console.print')
    def test_print_basic(self, mock_rich_print):
        """Test basic Console.print output path."""
        c = console_mod.Console()
        c.print("Test message")
        mock_rich_print.assert_called_once()
        args, kwargs = mock_rich_print.call_args
        self.assertIn("Test message", args[0])

    @patch('connectonion.console._rich_console.print')
    def test_print_with_style(self, mock_rich_print):
        """Test Console.print with style parameter."""
        c = console_mod.Console()
        c.print("Error occurred", style="red")
        mock_rich_print.assert_called_once()
        args, kwargs = mock_rich_print.call_args
        self.assertIn("Error occurred", args[0])


if __name__ == '__main__':
    unittest.main()
