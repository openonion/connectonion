"""Unit tests for connectonion/tool_executor.py"""

import unittest
from unittest.mock import Mock, patch
from connectonion.tool_executor import ToolExecutor


class TestToolExecutor(unittest.TestCase):
    """Test tool executor functionality."""

    def test_executor_initialization(self):
        """Test tool executor initialization."""
        executor = ToolExecutor()
        self.assertIsNotNone(executor)

    def test_execute_tool_success(self):
        """Test successful tool execution."""
        def sample_tool(x: int) -> int:
            """Sample tool."""
            return x * 2

        executor = ToolExecutor()
        result = executor.execute(sample_tool, {"x": 5})
        self.assertEqual(result, 10)

    def test_execute_tool_with_error(self):
        """Test tool execution with error."""
        def failing_tool():
            """Tool that fails."""
            raise ValueError("Tool error")

        executor = ToolExecutor()
        with self.assertRaises(ValueError):
            executor.execute(failing_tool, {})


if __name__ == '__main__':
    unittest.main()