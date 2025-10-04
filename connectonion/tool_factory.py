"""
Purpose: Convert Python functions and class methods into agent-compatible tool schemas
LLM-Note:
  Dependencies: imports from [inspect, functools, typing] | imported by [agent.py, __init__.py] | tested by [tests/test_tool_factory.py]
  Data flow: receives func: Callable → inspects signature with inspect.signature() → extracts type hints with get_type_hints() → maps Python types to JSON Schema via TYPE_MAP → creates tool with .name, .description, .to_function_schema(), .run() attributes → returns wrapped Callable
  State/Effects: no side effects | pure function transformations | preserves @xray and @replay decorator flags via hasattr checks | creates wrapper functions for bound methods to maintain self reference
  Integration: exposes create_tool_from_function(func), extract_methods_from_instance(obj), is_class_instance(obj) | used by Agent.__init__ to auto-convert tools | supports both standalone functions and bound methods | skips private methods (starting with _)
  Performance: uses inspect module (relatively fast) | TYPE_MAP provides O(1) type lookups | caches nothing (recreates on each call)
  Errors: skips methods without type annotations | skips methods without return type hint | handles inspection failures gracefully | wraps functions with functools.wraps to preserve metadata
"""

import inspect
import functools
from typing import Callable, Dict, Any, get_type_hints, List

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
        
        # Skip 'self' parameter for bound methods
        if param_name == 'self':
            continue
            
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
    
    # For bound methods, create a wrapper function that preserves the method
    if inspect.ismethod(func):
        base_func = getattr(func, "__func__", func)

        @functools.wraps(base_func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        # Preserve decorator flags from the underlying function (for backward compatibility)
        # Note: xray context is now injected for ALL tools automatically,
        # so @xray decorator is optional
        for attr in ("__xray_enabled__", "__replay_enabled__"):
            if hasattr(base_func, attr):
                try:
                    setattr(wrapper, attr, getattr(base_func, attr))
                except Exception:
                    pass

        # Ensure tool naming/docs are consistent for the Agent
        wrapper.__name__ = name
        wrapper.__doc__ = description
        tool_func = wrapper
    else:
        tool_func = func
    
    # Attach the necessary attributes for Agent compatibility
    tool_func.name = name
    tool_func.description = description
    tool_func.get_parameters_schema = lambda: parameters_schema
    tool_func.to_function_schema = lambda: {
        "name": name,
        "description": description,
        "parameters": parameters_schema,
    }
    tool_func.run = tool_func  # The agent calls .run() - this should be the decorated function
    
    return tool_func


def extract_methods_from_instance(instance) -> List[Callable]:
    """
    Extract public methods from a class instance that can be used as tools.
    
    Args:
        instance: A class instance to extract methods from
        
    Returns:
        List of method functions that have proper type annotations
    """
    methods = []
    
    for name in dir(instance):
        # Skip private methods (starting with _)
        if name.startswith('_'):
            continue
            
        attr = getattr(instance, name)
        
        # Check if it's a callable method (not a property or static value)
        if not callable(attr):
            continue
            
        # Skip built-in methods like __class__, etc.
        if isinstance(attr, type):
            continue
            
        # Check if it's actually a bound method (has __self__)
        if not hasattr(attr, '__self__'):
            continue
            
        # Check if method has proper type annotations
        try:
            sig = inspect.signature(attr)
            type_hints = get_type_hints(attr)
            
            # Must have return type annotation to be a valid tool
            if 'return' not in type_hints:
                continue
                
            # Process method as tool, preserving self reference
            tool = create_tool_from_function(attr)
            methods.append(tool)
            
        except (ValueError, TypeError):
            # Skip methods that can't be inspected
            continue
    
    return methods


def is_class_instance(obj) -> bool:
    """
    Check if an object is a class instance (not a function, class, or module).
    
    Args:
        obj: Object to check
        
    Returns:
        True if obj is a class instance with callable methods
    """
    # Must be an object with a class
    if not hasattr(obj, '__class__'):
        return False
        
    # Should not be a function, method, or class itself
    if inspect.isfunction(obj) or inspect.ismethod(obj) or inspect.isclass(obj):
        return False
        
    # Should not be a module
    if inspect.ismodule(obj):
        return False
        
    # Should not be built-in types
    if isinstance(obj, (list, dict, tuple, set, str, int, float, bool, type(None))):
        return False
        
    # Should have some callable attributes (methods)
    has_methods = any(
        callable(getattr(obj, name, None)) and not name.startswith('_')
        for name in dir(obj)
    )
    
    return has_methods