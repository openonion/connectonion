"""Tests for auto_debug_exception functionality."""

import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

# Add parent directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion.auto_debug_exception import auto_debug_exception


class TestAutoDebugException(unittest.TestCase):
    """Test auto_debug_exception functionality."""

    def setUp(self):
        """Set up test environment."""
        # Save original excepthook
        self.original_excepthook = sys.excepthook
        # Clear any environment variables
        os.environ.pop('CONNECTONION_AUTO_DEBUG', None)

    def tearDown(self):
        """Restore original state."""
        # Restore original excepthook
        sys.excepthook = self.original_excepthook
        # Clear environment
        os.environ.pop('CONNECTONION_AUTO_DEBUG', None)

    def test_auto_debug_exception_installs_hook(self):
        """Test that auto_debug_exception installs a custom exception hook."""
        # Check that hook is installed
        original_hook = sys.excepthook

        with patch('connectonion.console.Console'):
            auto_debug_exception()

        self.assertNotEqual(sys.excepthook, original_hook)

    def test_auto_debug_exception_respects_env_disable(self):
        """Test that auto_debug_exception respects CONNECTONION_AUTO_DEBUG=false."""
        # Set environment to disable
        os.environ['CONNECTONION_AUTO_DEBUG'] = 'false'

        # Save original hook
        original_hook = sys.excepthook

        # Call auto_debug_exception - should do nothing
        auto_debug_exception()

        # Hook should NOT be changed
        self.assertEqual(sys.excepthook, original_hook)

    def test_auto_debug_exception_confirmation_message(self):
        """Test auto_debug_exception shows confirmation message."""
        with patch('connectonion.console.Console') as mock_console:
            # Enable auto_debug
            auto_debug_exception()

            # Verify confirmation message
            mock_console.return_value.print.assert_called()
            # Get the actual call arguments
            calls = mock_console.return_value.print.call_args_list
            # Check that at least one call contains the expected message
            messages = [str(call) for call in calls]
            self.assertTrue(any("Exception debugging enabled" in msg for msg in messages))
            self.assertTrue(any("uncaught exceptions" in msg for msg in messages))

    @patch('connectonion.console.Console')
    def test_exception_handling_with_runtime_tools(self, mock_console_class):
        """Test that exceptions trigger runtime debug analysis."""
        with patch('connectonion.debug_agent.create_debug_agent') as mock_create_agent:
            # Setup mocks
            mock_console = Mock()
            mock_console_class.return_value = mock_console

            mock_agent = Mock()
            mock_agent.input.return_value = "Mock runtime analysis"
            mock_create_agent.return_value = mock_agent

            # Enable auto_debug_exception
            auto_debug_exception()

            # Create a test exception with some context
            def cause_error():
                data = {'key': 'value'}
                numbers = []
                return sum(numbers) / len(numbers)  # ZeroDivisionError

            try:
                cause_error()
            except ZeroDivisionError:
                exc_info = sys.exc_info()
                # Call the exception hook manually
                sys.excepthook(exc_info[0], exc_info[1], exc_info[2])

            # Verify create_debug_agent was called with frame and traceback
            mock_create_agent.assert_called_once()
            call_kwargs = mock_create_agent.call_args[1]
            self.assertIn('frame', call_kwargs)
            self.assertIn('exception_traceback', call_kwargs)
            self.assertIsNotNone(call_kwargs['frame'])
            self.assertIsNotNone(call_kwargs['exception_traceback'])

            # Verify prompt guides tool usage
            mock_agent.input.assert_called_once()
            prompt = mock_agent.input.call_args[0][0]
            self.assertIn("runtime inspection tools", prompt)
            self.assertIn("explore_namespace", prompt)
            self.assertIn("execute_in_frame", prompt)

            # Verify console output
            console_calls = [str(call) for call in mock_console.print.call_args_list]
            self.assertTrue(any("Analyzing with AI runtime inspection" in str(call) for call in console_calls))
            self.assertTrue(any("AI Runtime Debug Analysis" in str(call) for call in console_calls))

    def test_auto_debug_exception_handles_ai_failure_gracefully(self):
        """Test that auto_debug_exception handles AI analysis failure gracefully."""
        with patch('connectonion.console.Console') as mock_console_class:
            with patch('connectonion.debug_agent.create_debug_agent') as mock_create_agent:
                # Setup mock to raise an exception
                mock_create_agent.side_effect = Exception("AI service unavailable")

                mock_console = Mock()
                mock_console_class.return_value = mock_console

                # Enable auto_debug_exception
                auto_debug_exception()

                # Trigger an exception
                try:
                    1 / 0
                except ZeroDivisionError:
                    exc_info = sys.exc_info()
                    # Should not raise even if AI fails
                    sys.excepthook(exc_info[0], exc_info[1], exc_info[2])

                # Verify error message is shown
                console_calls = [str(call) for call in mock_console.print.call_args_list]
                self.assertTrue(any("AI analysis failed" in str(call) for call in console_calls))

    def test_auto_debug_exception_model_parameter(self):
        """Test that auto_debug_exception respects the model parameter."""
        with patch('connectonion.console.Console'):
            with patch('connectonion.debug_agent.create_debug_agent') as mock_create_agent:
                mock_agent = Mock()
                mock_agent.input.return_value = "Analysis"
                mock_create_agent.return_value = mock_agent

                # Enable with custom model
                auto_debug_exception(model="gpt-4")

                # Trigger exception
                try:
                    1 / 0
                except ZeroDivisionError:
                    exc_info = sys.exc_info()
                    sys.excepthook(exc_info[0], exc_info[1], exc_info[2])

                # Verify model was passed correctly
                mock_create_agent.assert_called()
                call_kwargs = mock_create_agent.call_args[1]
                self.assertEqual(call_kwargs['model'], "gpt-4")

    def test_exception_with_complex_data(self):
        """Test exception handling with complex nested data structures."""
        with patch('connectonion.console.Console') as mock_console_class:
            with patch('connectonion.debug_agent.create_debug_agent') as mock_create_agent:
                mock_console = Mock()
                mock_console_class.return_value = mock_console

                mock_agent = Mock()
                mock_agent.input.return_value = "Analysis of complex data"
                mock_create_agent.return_value = mock_agent

                # Enable auto_debug_exception
                auto_debug_exception()

                # Create complex exception scenario
                def complex_error():
                    users = [
                        {"name": "Alice", "age": 30, "settings": {"theme": "dark"}},
                        {"name": "Bob", "age": 25}
                    ]
                    # This will crash - Bob has no 'settings' key
                    for user in users:
                        theme = user["settings"]["theme"]

                try:
                    complex_error()
                except KeyError:
                    exc_info = sys.exc_info()
                    sys.excepthook(exc_info[0], exc_info[1], exc_info[2])

                # Verify agent was called
                mock_create_agent.assert_called_once()
                mock_agent.input.assert_called_once()

                # Check that prompt includes exception details
                prompt = mock_agent.input.call_args[0][0]
                self.assertIn("KeyError", prompt)

    def test_no_frame_found_handling(self):
        """Test handling when no relevant frame is found."""
        with patch('connectonion.console.Console') as mock_console_class:
            mock_console = Mock()
            mock_console_class.return_value = mock_console

            # Enable auto_debug_exception
            auto_debug_exception()

            # Create an exception with only system frames
            # This is a bit artificial but tests the edge case
            try:
                # Use eval to create a more "system-like" exception
                eval("1/0")
            except ZeroDivisionError:
                exc_info = sys.exc_info()
                # Manually call the hook
                sys.excepthook(exc_info[0], exc_info[1], exc_info[2])

            # Should handle gracefully even if no user frame found
            # Just verify it doesn't crash


if __name__ == '__main__':
    unittest.main()