"""Tool conversion utilities for ConnectOnion."""

import inspect
from typing import Callable, Dict, Any, get_type_hints

# Map Python types to JSON Schema types
TYPE_MAP = {
    str: "string",
    int: "integer", 
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}

def create_tool_from_function(func: Callable) -> Callable:
    """
    Converts a Python function into a tool that is compatible with the Agent,
    by inspecting its signature and docstring.
    """
    name = func.__name__
    description = inspect.getdoc(func) or f"Execute the {name} tool."

    # Build the parameters schema from the function signature
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)
    
    properties = {}
    required = []

    for param in sig.parameters.values():
        param_name = param.name
        # Use 'str' as a fallback if no type hint is available
        param_type = type_hints.get(param_name, str)
        schema_type = TYPE_MAP.get(param_type, "string")
        
        properties[param_name] = {"type": schema_type}

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    parameters_schema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters_schema["required"] = required
    
    # Attach the necessary attributes for Agent compatibility
    func.name = name
    func.description = description
    func.get_parameters_schema = lambda: parameters_schema
    func.to_function_schema = lambda: {
        "name": name,
        "description": description,
        "parameters": parameters_schema,
    }
    func.run = func  # The agent calls .run() - this should be the decorated function
    
    return func