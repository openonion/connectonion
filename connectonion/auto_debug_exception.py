"""
Purpose: Automatically analyze uncaught Python exceptions using AI with runtime frame inspection
LLM-Note:
  Dependencies: imports from [sys, traceback, os, dotenv, console.py, debug_agent/__init__.py] | imported by [__init__.py] | tested by [tests/test_auto_debug_exception.py]
  Data flow: auto_debug_exception() → installs sys.excepthook → on exception: calls original_hook (shows traceback) → finds relevant frame (last user code, not library) → extracts frame.f_locals → creates debug_agent with actual frame and traceback → sends prompt with exception details → agent uses runtime inspection tools (explore_namespace, execute_in_frame, inspect_object, validate_assumption, test_fix) → displays AI analysis
  State/Effects: modifies sys.excepthook globally | loads .env for CONNECTONION_AUTO_DEBUG | creates debug Agent instances on exceptions | calls console.print() to display analysis | does not prevent exception from terminating program
  Integration: exposes auto_debug_exception(model) | checks CONNECTONION_AUTO_DEBUG=false env to disable | creates debug_agent with frame, exception_traceback, model parameters | prompt guides AI to use runtime inspection tools
  Performance: only activates on exceptions (zero overhead in normal execution) | debug agent creates LLM instance per exception | runtime inspection executes code in crashed frame
  Errors: wraps AI analysis in try/except to avoid cascading failures | shows "AI analysis failed" message if agent crashes | handles missing frames gracefully | skips analysis if no relevant frame found
"""

import sys
import traceback
import os


def auto_debug_exception(model: str = "o4-mini"):
    """Enable AI debugging for uncaught exceptions ONLY.

    Debugs crashes, raised exceptions, and failed assertions. Does NOT debug
    logic errors, wrong outputs, or performance issues unless you convert them
    to exceptions using raise/assert.

    What gets debugged:
        ✅ Crashes: KeyError, TypeError, ZeroDivisionError, etc.
        ✅ Raised exceptions: raise ValueError("invalid input")
        ✅ Failed assertions: assert x > 0, "must be positive"
        ❌ Logic errors that don't raise exceptions

    Args:
        model: AI model to use (default: o4-mini for speed)

    Example:
        from connectonion import auto_debug_exception

        # Enable AI debugging for exceptions
        auto_debug_exception()

        # Any uncaught exception gets AI analysis with runtime data
        data = {"items": []}
        avg = sum(data["items"]) / len(data["items"])  # ZeroDivisionError!

    Environment:
        Set CONNECTONION_AUTO_DEBUG=false to disable even when called.
    """
    # Check if explicitly disabled via environment
    if os.environ.get('CONNECTONION_AUTO_DEBUG', '').lower() == 'false':
        return  # User explicitly disabled it

    # Save original hook for use in our handler
    original_hook = sys.excepthook

    def handle_exception(exc_type, exc_value, exception_traceback):
        """Handle an uncaught exception with AI runtime analysis."""
        # First call original hook to show normal traceback
        # (This ensures compatibility with other tools)
        original_hook(exc_type, exc_value, exception_traceback)

        # Then add our AI analysis
        from .console import Console
        console = Console()

        # Find the most relevant frame (last user code, not library)
        relevant_frame_info = None
        actual_frame = None
        actual_traceback = None
        current_traceback = exception_traceback

        while current_traceback:
            frame = current_traceback.tb_frame
            filename = frame.f_code.co_filename

            # Skip system/library files
            if not filename.startswith('<') and 'site-packages' not in filename:
                relevant_frame_info = {
                    'file': filename,
                    'line': current_traceback.tb_lineno,
                    'function': frame.f_code.co_name,
                    'locals': {}
                }
                # Keep the actual frame and traceback for runtime inspection
                actual_frame = frame
                actual_traceback = exception_traceback  # Keep the original traceback

                # Capture some local variables (simple types only) for display
                for name, value in frame.f_locals.items():
                    # Skip private/internal variables
                    if name.startswith('_'):
                        continue

                    # Only capture simple types to avoid huge dumps
                    if isinstance(value, (str, int, float, bool, type(None))):
                        relevant_frame_info['locals'][name] = value
                    elif isinstance(value, (list, dict, tuple)):
                        # Just show type and size
                        relevant_frame_info['locals'][name] = f"{type(value).__name__}({len(value)})"
                    else:
                        # Just show type
                        relevant_frame_info['locals'][name] = type(value).__name__

            current_traceback = current_traceback.tb_next

        # If no user code found, use the last frame
        if not relevant_frame_info and exception_traceback:
            last_traceback = exception_traceback
            while last_traceback.tb_next:
                last_traceback = last_traceback.tb_next

            frame = last_traceback.tb_frame
            relevant_frame_info = {
                'file': frame.f_code.co_filename,
                'line': last_traceback.tb_lineno,
                'function': frame.f_code.co_name,
                'locals': {}
            }
            actual_frame = frame
            actual_traceback = exception_traceback

        # Skip if no relevant frame
        if not relevant_frame_info:
            return

        # Run AI analysis with runtime inspection
        console.print("\n[yellow]🤖 Analyzing with AI runtime inspection...[/yellow]")

        try:
            # Use debug agent with runtime inspection tools
            from .debug_agent import create_debug_agent

            # Pass the actual frame and traceback for runtime inspection!
            agent = create_debug_agent(
                frame=actual_frame,
                exception_traceback=actual_traceback,
                model=model
            )

            # Build prompt that guides tool usage
            prompt = f"""Debug this Python exception using your runtime inspection tools:

Exception: {exc_type.__name__}: {exc_value}
File: {relevant_frame_info['file']}
Line: {relevant_frame_info['line']}
Function: {relevant_frame_info['function']}()

You have LIVE ACCESS to the crashed program's state! Use your tools to investigate:

1. First explore what variables are available:
   - Use explore_namespace() to see all variables

2. Then investigate the specific error:
   - Use execute_in_frame() to check values and types
   - Use inspect_object() to examine data structures
   - Use validate_assumption() to test your hypotheses

3. Test potential fixes:
   - Use test_fix() to verify solutions work with the actual data
   - Use try_alternative() to explore different approaches

4. Finally, provide your analysis:
   - **What I found**: Show the actual runtime values you discovered
   - **Why it failed**: Explain with evidence from the runtime state
   - **Verified fix**: A solution you tested that works"""

            # Get AI analysis
            result = agent.input(prompt)

            # Display the analysis
            console.print("\n[cyan bold]💡 AI Runtime Debug Analysis:[/cyan bold]")
            console.print(result)

        except Exception as e:
            # If AI analysis fails, show a simple message
            console.print(f"[dim]AI analysis failed: {e}[/dim]")

    # Install our exception hook
    sys.excepthook = handle_exception

    # Simple confirmation
    from .console import Console
    console = Console()
    console.print(f"[green]✅ Exception debugging enabled[/green] - AI will analyze uncaught exceptions with runtime inspection")