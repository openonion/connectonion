"""Debug tools for agent development and troubleshooting.

This module contains:
- xray: Runtime context injection for tool inspection
- decorators: replay, xray_replay for debugging
- auto_debug: Interactive debugging with breakpoints (AutoDebugger, AutoDebugUI)
- auto_debug_exception: Exception handling and debugging
- runtime_inspector: AI-powered runtime state inspection for crash debugging
- debug_explainer: AI-powered explanation of tool choices

Note: Uses lazy imports to avoid circular dependency with agent.py
"""

# xray and decorators can be imported eagerly (no circular dependency)
from .xray import xray
from .decorators import replay, xray_replay

__all__ = [
    "xray",
    "replay",
    "xray_replay",
    "AutoDebugger",
    "AutoDebugUI",
    "BreakpointContext",
    "BreakpointAction",
    "auto_debug_exception",
    "create_debug_agent",
    "RuntimeInspector",
    "explain_tool_choice",
    "RuntimeContext",
]


def __getattr__(name):
    """Lazy import to avoid circular dependency with agent.py."""
    if name == "AutoDebugger":
        from .auto_debug import AutoDebugger
        return AutoDebugger
    elif name in ("AutoDebugUI", "BreakpointContext", "BreakpointAction"):
        from .auto_debug_ui import AutoDebugUI, BreakpointContext, BreakpointAction
        return {"AutoDebugUI": AutoDebugUI, "BreakpointContext": BreakpointContext, "BreakpointAction": BreakpointAction}[name]
    elif name == "auto_debug_exception":
        from .auto_debug_exception import auto_debug_exception
        return auto_debug_exception
    elif name in ("create_debug_agent", "RuntimeInspector"):
        from .runtime_inspector import create_debug_agent, RuntimeInspector
        return {"create_debug_agent": create_debug_agent, "RuntimeInspector": RuntimeInspector}[name]
    elif name in ("explain_tool_choice", "RuntimeContext"):
        from .debug_explainer import explain_tool_choice, RuntimeContext
        return {"explain_tool_choice": explain_tool_choice, "RuntimeContext": RuntimeContext}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
