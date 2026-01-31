"""Prompt Assembler - Dynamic prompt composition with variable injection.

Similar to Claude Code's approach:
- Tool descriptions are injected based on available tools
- Variables like ${TOOL_NAME} are interpolated at runtime
- Conditional sections using ${condition ? "yes" : ""}
- System reminders can be injected based on agent state

Structure:
    prompts/
    ├── main.md           # Core agent behavior (with ${VARIABLES})
    ├── tools/            # Tool-specific guidance
    │   ├── shell.md
    │   └── ...
    ├── agents/           # Sub-agent prompts
    │   └── explore.md
    └── reminders/        # Runtime state reminders
        └── plan_mode.md
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional


class PromptContext:
    """Context object holding all variables for prompt interpolation."""
    
    def __init__(self):
        self._vars: Dict[str, Any] = {}
        self._tools: Dict[str, Any] = {}
        self._tool_set: set = set()
    
    def set(self, key: str, value: Any):
        """Set a variable value."""
        self._vars[key] = value
        return self
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a variable value."""
        return self._vars.get(key, default)
    
    def register_tool(self, tool: Any):
        """Register a tool and extract its name."""
        name = _get_tool_name(tool)
        self._tools[name] = tool
        self._tool_set.add(name)
        return self
    
    def has_tool(self, name: str) -> bool:
        """Check if a tool is available."""
        return name in self._tool_set
    
    def get_tool_names(self):
        """Get set of available tool names."""
        return self._tool_set
    
    def to_dict(self):
        """Export context as dict for interpolation."""
        result = dict(self._vars)
        result["AVAILABLE_TOOLS"] = self._tool_set
        result["has_tool"] = self.has_tool
        for name, tool in self._tools.items():
            result[f"{name.upper()}_TOOL"] = tool
        return result


def interpolate(template: str, context: Dict[str, Any]) -> str:
    """
    Interpolate variables in template string.
    
    Supports:
    - ${VAR_NAME} - simple variable substitution
    - ${has_tool("name") ? "yes" : "no"} - conditional based on tool availability
    - ${VAR_NAME or "default"} - default values
    
    Args:
        template: String with ${...} placeholders
        context: Dict of variable names to values
        
    Returns:
        Interpolated string
    """
    def replace_var(match: re.Match) -> str:
        expr = match.group(1).strip()
        
        # Handle ternary: condition ? "yes" : "no"
        ternary_match = re.match(r'(.+?)\s*\?\s*"([^"]*)"\s*:\s*"([^"]*)"', expr)
        if ternary_match:
            condition_expr, true_val, false_val = ternary_match.groups()
            condition_result = _eval_condition(condition_expr.strip(), context)
            return true_val if condition_result else false_val
        
        # Handle: VAR_NAME or "default"
        or_match = re.match(r'(\w+)\s+or\s+"([^"]*)"', expr)
        if or_match:
            var_name, default = or_match.groups()
            value = context.get(var_name)
            return str(value) if value else default
        
        # Simple variable lookup
        if expr in context:
            value = context[expr]
            if callable(value) and not isinstance(value, type):
                return str(value())
            return str(value) if value is not None else ""
        
        # Keep original if not found (for debugging)
        return match.group(0)
    
    # Match ${...} patterns, handling nested braces
    pattern = r'\$\{([^}]+)\}'
    return re.sub(pattern, replace_var, template)


def _eval_condition(expr: str, context: Dict[str, Any]) -> bool:
    """Evaluate a simple condition expression."""
    # Handle: has_tool("name")
    tool_check = re.match(r'has_tool\s*\(\s*"([^"]+)"\s*\)', expr)
    if tool_check:
        tool_name = tool_check.group(1)
        has_tool_fn = context.get("has_tool")
        if callable(has_tool_fn):
            return bool(has_tool_fn(tool_name))
        return tool_name in context.get("AVAILABLE_TOOLS", set())
    
    # Handle: VAR_NAME (truthy check)
    if expr in context:
        return bool(context[expr])
    
    # Handle: !VAR_NAME (falsy check)
    if expr.startswith("!") and expr[1:] in context:
        return not bool(context[expr[1:]])
    
    return False


def _get_tool_name(tool: Any) -> str:
    """Extract tool name from function or class instance."""
    if callable(tool) and hasattr(tool, "__name__"):
        return getattr(tool, "__name__")
    if hasattr(tool, "name"):
        return getattr(tool, "name")
    return tool.__class__.__name__


def assemble_prompt(
    prompts_dir: str,
    tools: Optional[List[Any]] = None,
    context: Optional[PromptContext] = None,
    extra_vars: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Assemble a system prompt from modular files with variable interpolation.

    Args:
        prompts_dir: Path to prompts directory
        tools: List of tool objects/functions (loads matching .md files)
        context: Optional PromptContext with pre-configured variables
        extra_vars: Additional variables to inject

    Returns:
        Assembled and interpolated prompt string
    """
    prompts_path = Path(prompts_dir)
    parts = []
    
    # Build context if not provided
    if context is None:
        context = PromptContext()
    
    # Register tools
    if tools:
        for tool in tools:
            context.register_tool(tool)
    
    # Add extra variables
    if extra_vars:
        for key, value in extra_vars.items():
            context.set(key, value)
    
    # Build interpolation dict
    ctx_dict = context.to_dict()
    
    # Add tool name mappings for convenience
    # e.g., SHELL_TOOL_NAME = "shell", READ_TOOL_NAME = "read_file"
    for name in context.get_tool_names():
        ctx_dict[f"{name.upper()}_TOOL_NAME"] = name
    
    # 1. Main prompt (required)
    main_file = prompts_path / "main.md"
    if main_file.exists():
        content = main_file.read_text()
        parts.append(interpolate(content, ctx_dict))

    # 2. Workflow (agent creation workflow)
    workflow_file = prompts_path / "workflow.md"
    if workflow_file.exists():
        content = workflow_file.read_text()
        parts.append(interpolate(content, ctx_dict))

    # 3. ConnectOnion framework prompt (index always included)
    co_index = prompts_path / "connectonion" / "index.md"
    if co_index.exists():
        content = co_index.read_text()
        parts.append(interpolate(content, ctx_dict))

    # 4. ConnectOnion examples (all loaded for one-shot correct)
    examples_dir = prompts_path / "connectonion" / "examples"
    if examples_dir.exists():
        for example_file in sorted(examples_dir.glob("*.md")):
            content = example_file.read_text()
            parts.append(interpolate(content, ctx_dict))

    # 5. Tool descriptions (for each available tool)
    tools_dir = prompts_path / "tools"
    if tools_dir.exists() and tools:
        for tool in tools:
            tool_name = _get_tool_name(tool).lower()
            tool_file = tools_dir / f"{tool_name}.md"
            if tool_file.exists():
                content = tool_file.read_text()
                parts.append(interpolate(content, ctx_dict))
    
    return "\n\n---\n\n".join(parts)


def load_reminder(
    prompts_dir: str,
    reminder_name: str,
    context: Optional[PromptContext] = None,
    extra_vars: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Load a system reminder for runtime injection.
    
    Reminders are state-specific prompts injected during conversation,
    wrapped in <system-reminder> tags.
    
    Args:
        prompts_dir: Path to prompts directory
        reminder_name: Name of the reminder (e.g., "plan_mode")
        context: Optional PromptContext for variable interpolation
        extra_vars: Additional variables to inject
        
    Returns:
        Formatted reminder string with <system-reminder> tags, or None if not found
    """
    reminders_dir = Path(prompts_dir) / "reminders"
    reminder_file = reminders_dir / f"{reminder_name}.md"
    
    if not reminder_file.exists():
        return None
    
    content = reminder_file.read_text()
    
    # Build interpolation context
    ctx_dict = {}
    if context:
        ctx_dict = context.to_dict()
    if extra_vars:
        ctx_dict.update(extra_vars)
    
    # Interpolate variables
    interpolated = interpolate(content, ctx_dict)
    
    return f"<system-reminder>\n{interpolated}\n</system-reminder>"


def load_agent_prompt(
    prompts_dir: str,
    agent_type: str,
    context: Optional[PromptContext] = None,
    extra_vars: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Load a sub-agent system prompt.

    Args:
        prompts_dir: Path to prompts directory
        agent_type: Type of agent (e.g., "explore", "plan")
        context: Optional PromptContext for variable interpolation
        extra_vars: Additional variables to inject

    Returns:
        Agent prompt string, or None if not found
    """
    agents_dir = Path(prompts_dir) / "agents"
    agent_file = agents_dir / f"{agent_type}.md"

    if not agent_file.exists():
        return None

    content = agent_file.read_text()

    # Build interpolation context
    ctx_dict = {}
    if context:
        ctx_dict = context.to_dict()
    if extra_vars:
        ctx_dict.update(extra_vars)

    return interpolate(content, ctx_dict)
