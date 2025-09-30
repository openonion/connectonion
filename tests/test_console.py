"""Unit tests for connectonion/console.py"""

import unittest
from unittest.mock import patch, Mock
from connectonion.console import log, error, success, warning


class TestConsole(unittest.TestCase):
    """Test console output functions."""

    @patch('builtins.print')
    def test_log_basic(self, mock_print):
        """Test basic log function."""
        log("Test message")
        mock_print.assert_called_once()

    @patch('builtins.print')
    def test_error_message(self, mock_print):
        """Test error message output."""
        error("Error occurred")
        mock_print.assert_called_once()
        # Check if error formatting is applied
        call_args = str(mock_print.call_args)
        self.assertIn("Error occurred", call_args)

    @patch('builtins.print')
    def test_success_message(self, mock_print):
        """Test success message output."""
        success("Operation successful")
        mock_print.assert_called_once()
        call_args = str(mock_print.call_args)
        self.assertIn("Operation successful", call_args)

    @patch('builtins.print')
    def test_warning_message(self, mock_print):
        """Test warning message output."""
        warning("Warning: proceed with caution")
        mock_print.assert_called_once()
        call_args = str(mock_print.call_args)
        self.assertIn("Warning", call_args)


if __name__ == '__main__':
    unittest.main()