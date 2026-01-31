"""Unit tests for connectonion/tool_factory.py"""

import pytest
from typing import Optional, List, Dict
from unittest.mock import Mock
from connectonion.core.tool_factory import create_tool_from_function, get_json_schema_type


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


class TestGetJsonSchemaType:
    """Test JSON schema type conversion for complex types."""

    def test_basic_string_type(self):
        """Test basic str type."""
        result = get_json_schema_type(str)
        assert result == {"type": "string"}

    def test_basic_int_type(self):
        """Test basic int type."""
        result = get_json_schema_type(int)
        assert result == {"type": "integer"}

    def test_basic_bool_type(self):
        """Test basic bool type."""
        result = get_json_schema_type(bool)
        assert result == {"type": "boolean"}

    def test_basic_list_type(self):
        """Test basic list type."""
        result = get_json_schema_type(list)
        assert result == {"type": "array"}

    def test_list_of_strings(self):
        """Test List[str] type."""
        result = get_json_schema_type(List[str])
        assert result == {"type": "array", "items": {"type": "string"}}

    def test_list_of_ints(self):
        """Test List[int] type."""
        result = get_json_schema_type(List[int])
        assert result == {"type": "array", "items": {"type": "integer"}}

    def test_optional_string(self):
        """Test Optional[str] type."""
        result = get_json_schema_type(Optional[str])
        assert result == {"type": "string"}

    def test_optional_list_of_strings(self):
        """Test Optional[List[str]] type - the main bug fix."""
        result = get_json_schema_type(Optional[List[str]])
        assert result == {"type": "array", "items": {"type": "string"}}

    def test_dict_type(self):
        """Test Dict type."""
        result = get_json_schema_type(Dict[str, int])
        assert result == {"type": "object"}

    def test_optional_dict(self):
        """Test Optional[Dict] type."""
        result = get_json_schema_type(Optional[Dict[str, str]])
        assert result == {"type": "object"}


class TestToolFactoryWithComplexTypes:
    """Test tool factory with complex type hints."""

    def test_function_with_optional_list(self):
        """Test tool creation with Optional[List[str]] parameter."""
        def ask_user(question: str, options: Optional[List[str]] = None) -> str:
            """Ask user a question."""
            return question

        tool = create_tool_from_function(ask_user)
        schema = tool.to_function_schema()

        assert schema["parameters"]["properties"]["options"] == {
            "type": "array",
            "items": {"type": "string"}
        }

    def test_function_with_list_param(self):
        """Test tool creation with List[str] parameter."""
        def process_items(items: List[str]) -> str:
            """Process items."""
            return ",".join(items)

        tool = create_tool_from_function(process_items)
        schema = tool.to_function_schema()

        assert schema["parameters"]["properties"]["items"] == {
            "type": "array",
            "items": {"type": "string"}
        }

    def test_function_with_dict_param(self):
        """Test tool creation with Dict parameter."""
        def process_data(data: Dict[str, int]) -> str:
            """Process data."""
            return str(data)

        tool = create_tool_from_function(process_data)
        schema = tool.to_function_schema()

        assert schema["parameters"]["properties"]["data"] == {"type": "object"}