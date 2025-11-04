"""Test tool fixtures for ConnectOnion tests.

This module provides both function-based and class-based tools for testing.
The agent supports both patterns:
- Functions: tools=[calculator, current_time]
- Class instances: tools=[CalculatorTool(), TimeTool()]
"""
import os
from datetime import datetime
from typing import Optional


# ============================================================================
# FUNCTION-BASED TOOLS (snake_case naming)
# ============================================================================

def calculator(expression: str) -> str:
    """Calculate mathematical expressions."""
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {str(e)}"


def current_time() -> str:
    """Get the current time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_file(filepath: str) -> str:
    """Read contents of a file."""
    try:
        if not os.path.exists(filepath):
            return f"Error: File not found: {filepath}"
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"


def write_file(filepath: str, content: str) -> str:
    """Write content to a file."""
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        return f"Successfully wrote to {filepath}"
    except Exception as e:
        return f"Error: {str(e)}"


def search_web(query: str, limit: Optional[int] = 5) -> str:
    """Mock web search tool."""
    return f"Search results for '{query}': [Result 1, Result 2, Result 3]"


# ============================================================================
# CLASS-BASED TOOLS (PascalCase naming)
# ============================================================================

class CalculatorTool:
    """Calculator tool as a class (methods become individual tools)."""

    def calculate(self, expression: str) -> str:
        """Calculate mathematical expressions."""
        try:
            result = eval(expression)
            return str(result)
        except Exception as e:
            return f"Error: {str(e)}"


class TimeTool:
    """Time tool as a class."""

    def get_current_time(self) -> str:
        """Get the current time."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FileReaderTool:
    """File operations tool as a class."""

    def read_file(self, filepath: str) -> str:
        """Read contents of a file."""
        try:
            if not os.path.exists(filepath):
                return f"Error: File not found: {filepath}"
            with open(filepath, 'r') as f:
                return f.read()
        except Exception as e:
            return f"Error: {str(e)}"

    def write_file(self, filepath: str, content: str) -> str:
        """Write content to a file."""
        try:
            with open(filepath, 'w') as f:
                f.write(content)
            return f"Successfully wrote to {filepath}"
        except Exception as e:
            return f"Error: {str(e)}"


# ============================================================================
# LEGACY ALIASES (for backward compatibility)
# ============================================================================

Calculator = calculator  # Function alias
CurrentTime = current_time
ReadFile = read_file
WriteFile = write_file
SearchWeb = search_web