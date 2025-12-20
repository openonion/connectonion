"""Unit tests for connectonion/tool_factory.py"""

import pytest
from unittest.mock import Mock
from connectonion.tool_factory import create_tool_from_function


class TestToolFactory:
    """Test tool factory functions."""

    def test_create_tool_from_simple_function(self):
        """Test creating tool from simple function."""
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        tool = create_tool_from_function(add)

        assert tool.name == "add"
        assert tool.description == "Add two numbers."
        assert tool.run(a=2, b=3) == 5

    def test_create_tool_with_optional_params(self):
        """Test creating tool with optional parameters."""
        def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone."""
            return f"{greeting}, {name}!"

        tool = create_tool_from_function(greet)

        assert tool.run(name="Alice") == "Hello, Alice!"
        assert tool.run(name="Bob", greeting="Hi") == "Hi, Bob!"

    def test_function_schema_generation(self):
        """Test that tool schemas are properly generated."""
        def calculate(x: int, y: int, operation: str) -> str:
            """Perform calculation."""
            return f"{x} {operation} {y}"

        tool = create_tool_from_function(calculate)
        schema = tool.to_function_schema()

        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema
        assert schema["name"] == "calculate"
        assert "x" in schema["parameters"]["properties"]
        assert "y" in schema["parameters"]["properties"]
        assert "operation" in schema["parameters"]["properties"]

    def test_tool_with_no_docstring(self):
        """Test tool creation with function that has no docstring."""
        def no_doc(x: int) -> int:
            return x * 2

        tool = create_tool_from_function(no_doc)

        assert tool.name == "no_doc"
        assert tool.description == "Execute the no_doc tool."

    def test_docstring_extracts_first_paragraph_only(self):
        """Test that only first paragraph of docstring is used (Args/Returns excluded)."""
        def search(query: str, limit: int = 10) -> str:
            """Search the web for information.

            Args:
                query: The search query string.
                limit: Maximum results to return.

            Returns:
                Search results as text.
            """
            return f"Results for {query}"

        tool = create_tool_from_function(search)

        # Should only have first paragraph, not Args/Returns
        assert tool.description == "Search the web for information."
        assert "Args" not in tool.description
        assert "Returns" not in tool.description

    def test_multiline_summary_extracted(self):
        """Test that multi-line first paragraph is preserved."""
        def complex_tool(data: str) -> str:
            """Process complex data with multiple steps.
This includes validation, transformation, and output formatting.

            Args:
                data: Input data to process.
            """
            return data

        tool = create_tool_from_function(complex_tool)

        # Multi-line summary should be joined
        assert "Process complex data" in tool.description
        assert "validation" in tool.description
        assert "Args" not in tool.description