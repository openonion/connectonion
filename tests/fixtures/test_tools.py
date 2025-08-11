"""Test tool fixtures for ConnectOnion tests."""
import os
from datetime import datetime
from typing import Optional


def Calculator(expression: str) -> str:
    """Calculate mathematical expressions."""
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {str(e)}"


def CurrentTime() -> str:
    """Get the current time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ReadFile(filepath: str) -> str:
    """Read contents of a file."""
    try:
        if not os.path.exists(filepath):
            return f"Error: File not found: {filepath}"
        with open(filepath, 'r') as f:
            return f.read()
    except Exception as e:
        return f"Error: {str(e)}"


def WriteFile(filepath: str, content: str) -> str:
    """Write content to a file."""
    try:
        with open(filepath, 'w') as f:
            f.write(content)
        return f"Successfully wrote to {filepath}"
    except Exception as e:
        return f"Error: {str(e)}"


def SearchWeb(query: str, limit: Optional[int] = 5) -> str:
    """Mock web search tool."""
    return f"Search results for '{query}': [Result 1, Result 2, Result 3]"