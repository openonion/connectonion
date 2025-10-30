"""Unit tests for connectonion/tool_factory.py"""

import unittest
from unittest.mock import Mock
from connectonion.tool_factory import create_tool_from_function


class TestToolFactory(unittest.TestCase):
    """Test tool factory functions."""

    def test_create_tool_from_simple_function(self):
        """Test creating tool from simple function."""
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        tool = create_tool_from_function(add)

        self.assertEqual(tool.name, "add")
        self.assertEqual(tool.description, "Add two numbers.")
        self.assertEqual(tool.run(a=2, b=3), 5)

    def test_create_tool_with_optional_params(self):
        """Test creating tool with optional parameters."""
        def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone."""
            return f"{greeting}, {name}!"

        tool = create_tool_from_function(greet)

        self.assertEqual(tool.run(name="Alice"), "Hello, Alice!")
        self.assertEqual(tool.run(name="Bob", greeting="Hi"), "Hi, Bob!")

    def test_function_schema_generation(self):
        """Test that tool schemas are properly generated."""
        def calculate(x: int, y: int, operation: str) -> str:
            """Perform calculation."""
            return f"{x} {operation} {y}"

        tool = create_tool_from_function(calculate)
        schema = tool.to_function_schema()

        self.assertIn("name", schema)
        self.assertIn("description", schema)
        self.assertIn("parameters", schema)
        self.assertEqual(schema["name"], "calculate")
        self.assertIn("x", schema["parameters"]["properties"])
        self.assertIn("y", schema["parameters"]["properties"])
        self.assertIn("operation", schema["parameters"]["properties"])

    def test_tool_with_no_docstring(self):
        """Test tool creation with function that has no docstring."""
        def no_doc(x: int) -> int:
            return x * 2

        tool = create_tool_from_function(no_doc)

        self.assertEqual(tool.name, "no_doc")
        self.assertIsNotNone(tool.description)


if __name__ == '__main__':
    unittest.main()