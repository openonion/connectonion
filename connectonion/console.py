"""
Purpose: Handle agent terminal output with Rich formatting and optional file logging
LLM-Note:
  Dependencies: imports from [sys, datetime, pathlib, typing, rich.console, rich.panel, rich.text] | imported by [agent.py, tool_executor.py, auto_debug_exception.py] | tested by [tests/test_console.py]
  Data flow: receives from Agent/tool_executor → .print(message, style) → formats with timestamp → prints to stderr via RichConsole → optionally appends to log_file as plain text
  State/Effects: writes to stderr (not stdout, to avoid mixing with agent results) | writes to log_file if provided (plain text with timestamps) | creates log file parent directories if needed | appends session separator on init
  Integration: exposes Console(log_file), .print(message, style), .print_xray_table(tool_name, tool_args, result, timing, agent) | used by Agent to show LLM/tool execution progress | tool_executor calls print_xray_table for @xray decorated tools
  Performance: direct stderr writes (no buffering delays) | Rich formatting uses stderr (separate from stdout results) | regex-based markup removal for log files
  Errors: no error handling (let I/O errors bubble up) | assumes log_file parent can be created | assumes stderr is available
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.text import Text

# Use stderr so console output doesn't mix with agent results
_rich_console = RichConsole(stderr=True)


class Console:
    """Console for agent output and optional file logging.

    Always shows output to help users understand what's happening.
    Similar to FastAPI, npm, cargo - always visible by default.
    """

    def __init__(self, log_file: Optional[Path] = None):
        """Initialize console.

        Args:
            log_file: Optional path to write logs (plain text)
        """
        self.log_file = log_file

        if self.log_file:
            self._init_log_file()

    def _init_log_file(self):
        """Initialize log file with session header."""
        # Create parent dirs if needed
        if self.log_file.parent != Path('.'):
            self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Add session separator
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Session started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'='*60}\n\n")

    def print(self, message: str, style: str = None):
        """Print message to console and/or log file.

        Always shows output to terminal. Optionally logs to file.

        Args:
            message: The message (can include Rich markup for console)
            style: Additional Rich style for console only
        """
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Always show terminal output with Rich formatting
        formatted = f"[dim]{timestamp}[/dim] {message}"
        if style:
            _rich_console.print(formatted, style=style)
        else:
            _rich_console.print(formatted)

        # Log file output (plain text) if enabled
        if self.log_file:
            plain = self._to_plain_text(message)
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {plain}\n")

    def print_xray_table(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Any,
        timing: float,
        agent: Any
    ) -> None:
        """Print Rich table for @xray decorated tools.

        Shows current tool execution details in a beautiful table format.

        Args:
            tool_name: Name of the tool that was executed
            tool_args: Arguments passed to the tool
            result: Result returned by the tool
            timing: Execution time in milliseconds
            agent: Agent instance with current_session
        """
        from rich.table import Table
        from rich.panel import Panel

        # Always print - console is always active
        from rich.text import Text
        from rich.console import Group

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="dim")
        table.add_column("Value")

        # Context information
        table.add_row("agent", agent.name)
        user_prompt = agent.current_session.get('user_prompt', '')
        prompt_preview = user_prompt[:50] + "..." if len(user_prompt) > 50 else user_prompt
        table.add_row("user_prompt", prompt_preview)
        iteration = agent.current_session.get('iteration', 0)
        max_iterations = getattr(agent, 'max_iterations', 10)
        table.add_row("iteration", f"{iteration}/{max_iterations}")

        # Separator
        table.add_row("─" * 20, "─" * 40)

        # Tool arguments
        for k, v in tool_args.items():
            val_str = str(v)
            if len(val_str) > 60:
                val_str = val_str[:60] + "..."
            table.add_row(k, val_str)

        # Result
        result_str = str(result)
        if len(result_str) > 60:
            result_str = result_str[:60] + "..."
        table.add_row("result", result_str)
        # Show more precision for fast operations (<0.1s), less for slow ones
        time_str = f"{timing/1000:.4f}s" if timing < 100 else f"{timing/1000:.1f}s"
        table.add_row("timing", time_str)

        # Add metadata footer
        metadata = Text(
            f"Execution time: {time_str} | Iteration: {iteration}/{max_iterations} | Breakpoint: @xray",
            style="dim italic",
            justify="center"
        )

        # Group table and metadata
        content = Group(table, Text(""), metadata)

        panel = Panel(content, title=f"[cyan]@xray: {tool_name}[/cyan]", border_style="cyan")
        _rich_console.print(panel)

        # Log to file if enabled (plain text version)
        if self.log_file:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n@xray: {tool_name}\n")
                f.write(f"  agent: {agent.name}\n")
                f.write(f"  task: {prompt_preview}\n")
                f.write(f"  iteration: {iteration}/{max_iterations}\n")
                for k, v in tool_args.items():
                    val_str = str(v)[:60]
                    f.write(f"  {k}: {val_str}\n")
                f.write(f"  result: {result_str}\n")
                f.write(f"  Execution time: {timing/1000:.4f}s | Iteration: {iteration}/{max_iterations} | Breakpoint: @xray\n\n")

    def _to_plain_text(self, message: str) -> str:
        """Convert Rich markup to plain text for log file."""
        # Remove Rich markup tags
        import re
        text = re.sub(r'\[/?\w+\]', '', message)

        # Convert common symbols
        text = text.replace('→', '->')
        text = text.replace('←', '<-')
        text = text.replace('✓', '[OK]')
        text = text.replace('✗', '[ERROR]')

        return text