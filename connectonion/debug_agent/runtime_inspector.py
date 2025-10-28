"""
Purpose: Provide runtime inspection tools for AI-powered exception debugging with live frame access
LLM-Note:
  Dependencies: imports from [pathlib, typing, re] | imported by [debug_agent/agent.py, debug_agent/__init__.py, auto_debug_exception.py] | tested by [tests/test_runtime_inspector.py]
  Data flow: auto_debug_exception() creates RuntimeInspector(frame, traceback) → stores frame.f_globals + frame.f_locals in self.namespace → AI agent calls methods: execute_in_frame(code) uses eval/exec, inspect_object(var) shows type/attrs/methods, validate_assumption(statement) tests hypothesis, test_fix(code) validates solutions, explore_namespace() lists all variables → returns formatted strings → AI interprets for debugging
  State/Effects: stores frozen exception frame and namespace | execute_in_frame() can modify namespace via exec | no file I/O or external side effects | evaluates arbitrary Python code (security: only in debug context)
  Integration: exposes RuntimeInspector class with methods: execute_in_frame(code), inspect_object(variable_name), validate_assumption(statement), test_fix(fix_code), try_alternative(code), explore_namespace(), get_traceback() | used as class-based tool (Agent auto-extracts methods via tool_factory.extract_methods_from_instance)
  Performance: eval/exec are fast | namespace is dict copy (O(n) initial cost) | inspection uses dir() and getattr() | traceback formatting uses traceback module
  Errors: execute_in_frame() catches exceptions and returns error strings (doesn't raise) | missing variables return "not found" messages | no frame returns "No runtime context available"
"""

from pathlib import Path
from typing import Any, Optional, List, Dict
import re


class RuntimeInspector:
    """Inspector that operates on a frozen exception runtime state.

    Pass an instance of this class directly to the Agent as a tool.
    ConnectOnion will automatically discover all public methods!
    """

    def __init__(self, frame=None, exception_traceback=None):
        """Initialize with optional exception frame and traceback.

        Args:
            frame: The frame object where the exception occurred
            exception_traceback: The traceback object from the exception
        """
        self.frame = frame
        self.exception_traceback = exception_traceback
        self.namespace = {}

        if frame:
            # Combine locals and globals for execution context
            self.namespace.update(frame.f_globals)
            self.namespace.update(frame.f_locals)

    def set_context(self, frame, exception_traceback):
        """Update the runtime context (called by auto_debug).

        Args:
            frame: The frame object where the exception occurred
            exception_traceback: The traceback object from the exception
        """
        self.frame = frame
        self.exception_traceback = exception_traceback
        self.namespace = {}
        self.namespace.update(frame.f_globals)
        self.namespace.update(frame.f_locals)

    def execute_in_frame(self, code: str) -> str:
        """Execute Python code in the exception frame context.

        Access all variables, call functions, and test hypotheses with real data.

        Args:
            code: Python code to execute in the exception frame

        Returns:
            The result of execution or error message

        Examples:
            execute_in_frame("type(profile)")
            execute_in_frame("list(data.keys())")
            execute_in_frame("profile.get('name', 'default')")
        """
        if not self.frame:
            return "No runtime context available"

        try:
            result = eval(code, self.namespace)
            return self._format_result(result)
        except Exception as e:
            # Try exec for statements (like assignments)
            try:
                exec(code, self.namespace)
                return "Executed successfully"
            except Exception:
                return f"Error: {e}"

    def inspect_object(self, variable_name: str) -> str:
        """Deep inspection of an object in the runtime context.

        Shows the object's type, attributes, methods, and current state.

        Args:
            variable_name: Name of the variable to inspect

        Returns:
            Detailed information about the object

        Example:
            inspect_object("profile")
        """
        if not self.frame:
            return "No runtime context available"

        if variable_name not in self.namespace:
            return f"Variable '{variable_name}' not found in scope"

        obj = self.namespace[variable_name]
        result = [f"=== {variable_name} ==="]
        result.append(f"Type: {type(obj).__name__}")
        result.append(f"Value: {self._format_result(obj, max_length=200)}")

        # Type-specific details
        if isinstance(obj, dict):
            result.append(f"Keys ({len(obj)}): {list(obj.keys())[:10]}")
            if len(obj) > 10:
                result.append(f"  ... +{len(obj) - 10} more")
        elif isinstance(obj, (list, tuple)):
            result.append(f"Length: {len(obj)}")
            if obj:
                result.append(f"First: {self._format_result(obj[0], max_length=100)}")
        elif hasattr(obj, '__dict__'):
            attrs = vars(obj)
            result.append(f"Attributes: {list(attrs.keys())[:10]}")

        # Show methods (non-private)
        methods = [m for m in dir(obj)
                  if not m.startswith('_') and callable(getattr(obj, m, None))]
        if methods:
            result.append(f"Methods: {methods[:10]}")
            if len(methods) > 10:
                result.append(f"  ... +{len(methods) - 10} more")

        return "\n".join(result)

    def test_fix(self, original_code: str, fixed_code: str) -> str:
        """Test a potential fix using the actual runtime data.

        Compare what the original code produced vs what the fix would produce.

        Args:
            original_code: The code that caused the error
            fixed_code: The proposed fix to test

        Returns:
            Comparison of results from both versions

        Example:
            test_fix("data['key']", "data.get('key', 'default')")
        """
        if not self.frame:
            return "No runtime context available"

        result = ["=== Testing Fix ==="]

        # Test original
        result.append(f"\nOriginal: {original_code}")
        try:
            original_result = eval(original_code, self.namespace)
            result.append(f"  → {self._format_result(original_result)}")
        except Exception as e:
            result.append(f"  ✗ {e}")

        # Test fix
        result.append(f"\nFixed: {fixed_code}")
        try:
            fixed_result = eval(fixed_code, self.namespace)
            result.append(f"  → {self._format_result(fixed_result)}")
            result.append("  ✓ Fix works!")
        except Exception as e:
            result.append(f"  ✗ {e}")

        return "\n".join(result)

    def validate_assumption(self, assumption: str) -> str:
        """Validate an assumption about the runtime state.

        Test any assumption using the actual data.

        Args:
            assumption: Python expression that should return True/False

        Returns:
            Whether the assumption holds and details

        Examples:
            validate_assumption("isinstance(profile, dict)")
            validate_assumption("'notifications' in profile")
            validate_assumption("len(items) > 0")
        """
        if not self.frame:
            return "No runtime context available"

        result = [f"=== Validating: {assumption} ==="]

        try:
            validation_result = eval(assumption, self.namespace)

            if validation_result is True:
                result.append("✓ TRUE")
            elif validation_result is False:
                result.append("✗ FALSE")
            else:
                result.append(f"Result: {self._format_result(validation_result)} (not boolean)")

            # Add helpful context
            self._add_validation_context(assumption, result)

        except Exception as e:
            result.append(f"Error: {e}")

        return "\n".join(result)

    def trace_variable(self, variable_name: str) -> str:
        """Trace how a variable changed through the call stack.

        Shows the variable's value in each frame of the call stack.

        Args:
            variable_name: Name of the variable to trace

        Returns:
            The variable's values through the call stack

        Example:
            trace_variable("user_data")
        """
        if not self.exception_traceback:
            return "No traceback available"

        result = [f"=== Tracing '{variable_name}' ==="]

        frame_num = 0
        current_traceback = self.exception_traceback

        while current_traceback:
            frame = current_traceback.tb_frame
            frame_num += 1

            func_name = frame.f_code.co_name
            filename = Path(frame.f_code.co_filename).name
            line_no = current_traceback.tb_lineno

            result.append(f"\n#{frame_num} {func_name}() at {filename}:{line_no}")

            if variable_name in frame.f_locals:
                value = frame.f_locals[variable_name]
                result.append(f"  {variable_name} = {self._format_result(value)}")
            else:
                result.append(f"  (not in scope)")

            current_traceback = current_traceback.tb_next

        return "\n".join(result)

    def explore_namespace(self) -> str:
        """Explore all available variables in the exception context.

        Returns:
            List of all variables and their types
        """
        if not self.frame:
            return "No runtime context available"

        result = ["=== Available Variables ==="]

        # Group by type for better organization
        by_type: Dict[str, List[str]] = {}

        for name, value in self.namespace.items():
            if name.startswith('__'):
                continue  # Skip dunder variables

            type_name = type(value).__name__
            if type_name not in by_type:
                by_type[type_name] = []
            by_type[type_name].append(name)

        # Show variables grouped by type
        for type_name in sorted(by_type.keys()):
            vars_list = by_type[type_name][:10]  # Limit to 10 per type
            if len(by_type[type_name]) > 10:
                vars_list.append(f"... +{len(by_type[type_name]) - 10} more")
            result.append(f"\n{type_name}: {', '.join(vars_list)}")

        return "\n".join(result)

    def try_alternative(self, failing_expr: str, *alternatives: str) -> str:
        """Try multiple alternative expressions to find what works.

        Useful for exploring different ways to access data.

        Args:
            failing_expr: The expression that's failing
            *alternatives: Alternative expressions to try

        Returns:
            Results of all attempts

        Example:
            try_alternative(
                "data['key']",
                "data.get('key')",
                "data.get('Key')",  # Different case
                "data.get('keys')"  # Plural
            )
        """
        if not self.frame:
            return "No runtime context available"

        result = ["=== Trying Alternatives ==="]

        # Test original
        result.append(f"\nOriginal: {failing_expr}")
        try:
            orig_result = eval(failing_expr, self.namespace)
            result.append(f"  ✓ Works: {self._format_result(orig_result)}")
        except Exception as e:
            result.append(f"  ✗ {e}")

        # Test alternatives
        for alt in alternatives:
            result.append(f"\nAlternative: {alt}")
            try:
                alt_result = eval(alt, self.namespace)
                result.append(f"  ✓ Works: {self._format_result(alt_result)}")
            except Exception as e:
                result.append(f"  ✗ {e}")

        return "\n".join(result)

    def read_source_around_error(self, context_lines: int = 5) -> str:
        """Read source code around the error location.

        Args:
            context_lines: Number of lines before and after to show

        Returns:
            Source code with line numbers, highlighting the error line
        """
        if not self.exception_traceback:
            return "No traceback available"

        # Get the file and line from the traceback
        current_traceback = self.exception_traceback
        while current_traceback.tb_next:  # Go to the last frame
            current_traceback = current_traceback.tb_next

        filename = current_traceback.tb_frame.f_code.co_filename
        line_number = current_traceback.tb_lineno

        try:
            path = Path(filename)
            if not path.exists():
                return f"File not found: {filename}"

            with open(path, 'r') as f:
                lines = f.readlines()

            start = max(0, line_number - context_lines - 1)
            end = min(len(lines), line_number + context_lines)

            result = [f"=== {path.name}:{line_number} ===\n"]
            for i in range(start, end):
                line_num = i + 1
                prefix = ">>>" if line_num == line_number else "   "
                result.append(f"{prefix} {line_num:4}: {lines[i].rstrip()}")

            return "\n".join(result)
        except Exception as e:
            return f"Error reading source: {e}"

    def _format_result(self, obj: Any, max_length: int = 500) -> str:
        """Format an object for display."""
        if obj is None:
            return "None"
        elif isinstance(obj, (str, int, float, bool)):
            result = repr(obj)
        elif isinstance(obj, (list, dict, tuple)):
            result = repr(obj)
        else:
            result = f"{type(obj).__name__}: {str(obj)}"

        if len(result) > max_length:
            result = result[:max_length] + "..."
        return result

    def _add_validation_context(self, assumption: str, result: list):
        """Add helpful context for validation results."""
        # For isinstance checks, show actual type
        if "isinstance" in assumption:
            match = re.match(r'isinstance\((\w+),', assumption)
            if match:
                var_name = match.group(1)
                if var_name in self.namespace:
                    actual_type = type(self.namespace[var_name]).__name__
                    result.append(f"  Actual type: {actual_type}")

        # For membership tests, show available options
        if " in " in assumption:
            parts = assumption.split(" in ")
            if len(parts) == 2:
                container_code = parts[1].strip().rstrip(')')
                try:
                    container = eval(container_code, self.namespace)
                    if isinstance(container, dict):
                        result.append(f"  Available keys: {list(container.keys())[:10]}")
                    elif isinstance(container, (list, tuple, set)):
                        result.append(f"  Contains {len(container)} items")
                except:
                    pass