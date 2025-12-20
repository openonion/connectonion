"""Tests for RuntimeInspector class."""

import sys
import pytest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from connectonion.debug.runtime_inspector.runtime_inspector import RuntimeInspector


class TestRuntimeInspector:
    """Test RuntimeInspector functionality."""

    def create_test_frame(self):
        """Create a test frame with some local variables."""
        # Create variables in a function to get a frame
        def test_function():
            test_string = "hello"
            test_number = 42
            test_list = [1, 2, 3]
            test_dict = {"key": "value", "count": 10}
            test_none = None

            # Get the current frame
            import inspect
            return inspect.currentframe()

        return test_function()

    def create_test_traceback(self):
        """Create a test traceback."""
        try:
            def inner():
                x = 10
                y = 0
                return x / y  # ZeroDivisionError

            def outer():
                result = inner()
                return result

            outer()
        except ZeroDivisionError:
            import sys
            return sys.exc_info()[2]

    def test_runtime_inspector_init(self):
        """Test RuntimeInspector initialization."""
        frame = self.create_test_frame()
        traceback = self.create_test_traceback()

        inspector = RuntimeInspector(frame=frame, exception_traceback=traceback)

        assert inspector.frame is not None
        assert inspector.exception_traceback is not None
        assert inspector.namespace is not None
        assert "test_string" in inspector.namespace
        assert inspector.namespace["test_string"] == "hello"

    def test_execute_in_frame(self):
        """Test executing code in the frame context."""
        frame = self.create_test_frame()
        inspector = RuntimeInspector(frame=frame)

        # Test simple expression
        result = inspector.execute_in_frame("test_number * 2")
        assert result == "84"

        # Test accessing variables
        result = inspector.execute_in_frame("test_string.upper()")
        assert result == "'HELLO'"

        # Test list operations
        result = inspector.execute_in_frame("len(test_list)")
        assert result == "3"

        # Test dict access
        result = inspector.execute_in_frame("test_dict['key']")
        assert result == "'value'"

    def test_execute_in_frame_with_error(self):
        """Test execute_in_frame handles errors gracefully."""
        frame = self.create_test_frame()
        inspector = RuntimeInspector(frame=frame)

        # Test undefined variable
        result = inspector.execute_in_frame("undefined_variable")
        assert "Error" in result
        assert "undefined_variable" in result

        # Test invalid syntax
        result = inspector.execute_in_frame("invalid syntax here")
        assert "Error" in result

    def test_inspect_object(self):
        """Test inspecting objects in the runtime context."""
        frame = self.create_test_frame()
        inspector = RuntimeInspector(frame=frame)

        # Inspect dictionary
        result = inspector.inspect_object("test_dict")
        assert "dict" in result
        assert "Keys (2)" in result
        assert "key" in result
        assert "count" in result

        # Inspect list
        result = inspector.inspect_object("test_list")
        assert "list" in result
        assert "Length: 3" in result
        assert "First: 1" in result

        # Inspect string
        result = inspector.inspect_object("test_string")
        assert "str" in result
        assert "hello" in result

    def test_inspect_object_not_found(self):
        """Test inspecting non-existent object."""
        frame = self.create_test_frame()
        inspector = RuntimeInspector(frame=frame)

        result = inspector.inspect_object("non_existent_variable")
        assert "not found" in result

    def test_test_fix(self):
        """Test the test_fix method."""
        frame = self.create_test_frame()
        inspector = RuntimeInspector(frame=frame)

        # Test a fix that works
        result = inspector.test_fix(
            "test_dict['missing_key']",  # This would fail
            "test_dict.get('missing_key', 'default')"  # This works
        )

        assert "Testing Fix" in result
        assert "Original:" in result
        assert "✗" in result  # Original fails (marked with ✗)
        assert "Fixed:" in result
        assert "'default'" in result  # Fixed returns default
        assert "✓ Fix works!" in result

    def test_validate_assumption(self):
        """Test validating assumptions."""
        frame = self.create_test_frame()
        inspector = RuntimeInspector(frame=frame)

        # Test true assumption
        result = inspector.validate_assumption("isinstance(test_dict, dict)")
        assert "✓ TRUE" in result

        # Test false assumption
        result = inspector.validate_assumption("isinstance(test_string, int)")
        assert "✗ FALSE" in result
        assert "Actual type: str" in result

        # Test membership check
        result = inspector.validate_assumption("'key' in test_dict")
        assert "✓ TRUE" in result

        result = inspector.validate_assumption("'missing' in test_dict")
        assert "✗ FALSE" in result
        assert "Available keys" in result

    def test_explore_namespace(self):
        """Test exploring available variables."""
        frame = self.create_test_frame()
        inspector = RuntimeInspector(frame=frame)

        result = inspector.explore_namespace()

        assert "Available Variables" in result
        assert "str:" in result
        assert "test_string" in result
        assert "int:" in result
        assert "test_number" in result
        assert "list:" in result
        assert "test_list" in result
        assert "dict:" in result
        assert "test_dict" in result

    def test_try_alternative(self):
        """Test trying alternative expressions."""
        frame = self.create_test_frame()
        inspector = RuntimeInspector(frame=frame)

        result = inspector.try_alternative(
            "test_dict['missing']",  # Fails
            "test_dict.get('missing')",  # Returns None
            "test_dict.get('key')",  # Works
            "test_dict['key']"  # Also works
        )

        assert "Trying Alternatives" in result
        assert "Original:" in result
        assert "✗" in result  # Original fails (marked with ✗)
        assert "Alternative:" in result
        assert "✓ Works: 'value'" in result  # Some alternatives work

    def test_trace_variable(self):
        """Test tracing a variable through the call stack."""
        # Create a traceback with variable in multiple frames
        try:
            def level3():
                data = "level3"
                return 1 / 0

            def level2():
                data = "level2"
                return level3()

            def level1():
                data = "level1"
                return level2()

            level1()
        except ZeroDivisionError:
            exc_info = sys.exc_info()
            frame = exc_info[2].tb_frame
            traceback = exc_info[2]

            inspector = RuntimeInspector(frame=frame, exception_traceback=traceback)

            result = inspector.trace_variable("data")

            assert "Tracing 'data'" in result
            # Should show data variable in different frames
            # Note: exact content depends on how frames are captured

    def test_read_source_around_error(self):
        """Test reading source code around error."""
        traceback = self.create_test_traceback()
        inspector = RuntimeInspector(exception_traceback=traceback)

        result = inspector.read_source_around_error(context_lines=3)

        assert ">>>" in result  # Error line marker
        assert "return x / y" in result  # The actual error line

    def test_no_frame_context(self):
        """Test methods handle missing frame gracefully."""
        inspector = RuntimeInspector()  # No frame or traceback

        # All methods should return appropriate error messages
        result = inspector.execute_in_frame("1 + 1")
        assert "No runtime context" in result

        result = inspector.inspect_object("anything")
        assert "No runtime context" in result

        result = inspector.test_fix("a", "b")
        assert "No runtime context" in result

        result = inspector.validate_assumption("True")
        assert "No runtime context" in result

        result = inspector.explore_namespace()
        assert "No runtime context" in result

        result = inspector.try_alternative("a", "b")
        assert "No runtime context" in result

    def test_set_context(self):
        """Test updating the runtime context."""
        inspector = RuntimeInspector()

        # Initially no context
        result = inspector.execute_in_frame("1 + 1")
        assert "No runtime context" in result

        # Set context
        frame = self.create_test_frame()
        traceback = self.create_test_traceback()
        inspector.set_context(frame, traceback)

        # Now should work
        result = inspector.execute_in_frame("test_number")
        assert result == "42"