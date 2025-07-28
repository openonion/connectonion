"""Tools interface and built-in tools for ConnectOnion."""

from abc import ABC, abstractmethod
from typing import Dict, Any
from datetime import datetime
import json


class Tool(ABC):
    """Base class for all tools."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    @abstractmethod
    def run(self, **kwargs) -> str:
        """Execute the tool with given parameters."""
        pass
    
    def to_function_schema(self) -> Dict[str, Any]:
        """Convert tool to OpenAI function schema format."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameters_schema()
        }
    
    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """Return JSON schema for tool parameters."""
        pass


class Calculator(Tool):
    """Tool for performing mathematical calculations."""
    
    def __init__(self):
        super().__init__(
            name="calculator",
            description="Perform mathematical calculations. Supports +, -, *, /, ** operations."
        )
    
    def run(self, expression: str) -> str:
        """Execute mathematical expression safely."""
        try:
            # Only allow safe operations
            allowed_chars = "0123456789+-*/().**"
            if all(c in allowed_chars + " " for c in expression):
                result = eval(expression)
                return f"Result: {result}"
            else:
                return "Error: Invalid characters in expression"
        except Exception as e:
            return f"Error: {str(e)}"
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate"
                }
            },
            "required": ["expression"]
        }


class CurrentTime(Tool):
    """Tool for getting current date and time."""
    
    def __init__(self):
        super().__init__(
            name="current_time",
            description="Get the current date and time"
        )
    
    def run(self, format: str = "%Y-%m-%d %H:%M:%S") -> str:
        """Return current time in specified format."""
        return datetime.now().strftime(format)
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "Time format string (default: %Y-%m-%d %H:%M:%S)"
                }
            }
        }


class ReadFile(Tool):
    """Tool for reading file contents."""
    
    def __init__(self):
        super().__init__(
            name="read_file",
            description="Read contents of a text file"
        )
    
    def run(self, filepath: str) -> str:
        """Read and return file contents."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return content if content else "File is empty"
        except FileNotFoundError:
            return f"Error: File '{filepath}' not found"
        except Exception as e:
            return f"Error reading file: {str(e)}"
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the file to read"
                }
            },
            "required": ["filepath"]
        }