"""
Purpose: Handle agent terminal output with Rich formatting and optional file logging
LLM-Note:
  Dependencies: imports from [sys, datetime, pathlib, typing, rich.console, rich.panel, rich.text] | imported by [logger.py, tool_executor.py] | tested by [tests/test_console.py]
  Data flow: receives from Logger/tool_executor → .print(), .log_tool_call(), .log_tool_result() → formats with timestamp → prints to stderr via RichConsole → optionally appends to log_file as plain text
  State/Effects: writes to stderr (not stdout, to avoid mixing with agent results) | writes to log_file if provided (plain text with timestamps) | creates log file parent directories if needed | appends session separator on init
  Integration: exposes Console(log_file), .print(message, style), .log_tool_call(name, args), .log_tool_result(result, timing), .log_llm_response(), .print_xray_table() | tool calls formatted as natural function-call style: greet(name='Alice')
  Performance: direct stderr writes (no buffering delays) | Rich formatting uses stderr (separate from stdout results) | regex-based markup removal for log files
  Errors: no error handling (let I/O errors bubble up) | assumes log_file parent can be created | assumes stderr is available
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.text import Text
from rich.markup import escape as rich_escape

# Use stderr so console output doesn't mix with agent results
_rich_console = RichConsole(stderr=True)

# Brand constants
BRAND_COLOR = "cyan"
PREFIX = "[co]"

# Onion layer symbols (ties to banner ○ ◎ ●)
CIRCLE_EMPTY = "○"      # Request/waiting
CIRCLE_FILLED = "●"     # Response/complete

# Other symbols
TOOL_SYMBOL = "▸"       # Tool execution
SUCCESS_SYMBOL = "✓"    # Action success (tools)
LLM_DONE_SYMBOL = "⚡"   # LLM thinking complete (flash)
ERROR_SYMBOL = "✗"      # Error

# Color scheme - brand + semantic
# Cyan = brand identity ([co], banner)
# Violet = LLM/AI thinking (○ ●)
# Green = tool action (▸) and success (✓)
LLM_COLOR = "magenta"       # Violet for LLM thinking
TOOL_COLOR = "green"        # Green for tool action
SUCCESS_COLOR = "green"     # Success indicators
ERROR_COLOR = "red"         # Errors
DIM_COLOR = "dim"           # Metadata (tokens, cost, time)


def _get_version() -> str:
    """Get version from package, with fallback."""
    from . import __version__
    return __version__


def _prefix() -> str:
    """Get formatted [co] prefix.

    Uses rich_escape to render literal [co] brackets in cyan.
    """
    return f"[{BRAND_COLOR}]{rich_escape(PREFIX)}[/{BRAND_COLOR}]"


def _plain_prefix() -> str:
    """Get plain text prefix for log files."""
    return PREFIX


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

    def print_banner(
        self,
        agent_name: str,
        model: str = "",
        tools: Union[List[str], int] = 0,
        log_dir: Optional[str] = None,
        llm: Any = None
    ) -> None:
        """Print the ConnectOnion banner (Onion Stack style).

          ○
         ◎    research-assistant
        ●     ─────────────────────
              connectonion v0.5.1
              o4-mini · 3 tools
              .co/logs/ · .co/sessions/

        Args:
            agent_name: Name of the agent
            model: Model name (e.g., "co/o4-mini")
            tools: List of tool names or count of tools
            log_dir: Log directory path (e.g., ".co/")
            llm: LLM instance to check for free tier
        """
        version = _get_version()

        # Calculate tools display
        if isinstance(tools, list):
            tools_count = len(tools)
        else:
            tools_count = tools
        tools_str = f"{tools_count} tool{'s' if tools_count != 1 else ''}" if tools_count else ""

        # Build meta line: model · tools
        meta_parts = [p for p in [model, tools_str] if p]
        meta_line = " · ".join(meta_parts)

        # Check if using OpenOnion managed keys (free credits from Aaron)
        is_free_tier = False
        if llm is not None:
            is_free_tier = type(llm).__name__ == "OpenOnionLLM"
        aaron_message = "credits on me, go build —aaron" if is_free_tier else None

        # Calculate separator length (at least as long as agent name, min 20)
        separator_len = max(len(agent_name), 20)
        separator = "─" * separator_len

        # Build the banner lines with Rich markup (Onion Stack - descending layers)
        lines = [
            f"  [{BRAND_COLOR}]{CIRCLE_EMPTY}[/{BRAND_COLOR}]",
            f" [{BRAND_COLOR}]◎[/{BRAND_COLOR}]    [bold]{agent_name}[/bold]",
            f"[{BRAND_COLOR}]{CIRCLE_FILLED}[/{BRAND_COLOR}]     [{DIM_COLOR}]{separator}[/{DIM_COLOR}]",
            f"      [{BRAND_COLOR}]connectonion[/{BRAND_COLOR}] [{DIM_COLOR}]v{version}[/{DIM_COLOR}]",
        ]

        # Add meta line if there's content
        if meta_line:
            lines.append(f"      [{DIM_COLOR}]{meta_line}[/{DIM_COLOR}]")

        # Add log paths if logging is enabled
        if log_dir:
            lines.append(f"      [{DIM_COLOR}]{log_dir}logs/ · {log_dir}sessions/[/{DIM_COLOR}]")

        # Add Aaron's message for free tier users
        if aaron_message:
            lines.append(f"      [{DIM_COLOR}]{aaron_message}[/{DIM_COLOR}]")

        # Add closing separator
        lines.append(f"      [{DIM_COLOR}]{separator}[/{DIM_COLOR}]")

        # Print with empty line before and after for breathing room
        _rich_console.print()
        for line in lines:
            _rich_console.print(line)
        _rich_console.print()

        # Log to file (plain text version)
        if self.log_file:
            plain_lines = [
                f"  {CIRCLE_EMPTY}",
                f" ◎    {agent_name}",
                f"{CIRCLE_FILLED}     {separator}",
                f"      connectonion v{version}",
            ]
            if meta_line:
                plain_lines.append(f"      {meta_line}")
            if log_dir:
                plain_lines.append(f"      {log_dir}logs/ · {log_dir}sessions/")
            if aaron_message:
                plain_lines.append(f"      {aaron_message}")
            plain_lines.append(f"      {separator}")

            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("\n")
                for line in plain_lines:
                    f.write(f"{line}\n")
                f.write("\n")

    def print(self, message: str, style: str = None, use_prefix: bool = True):
        """Print message to console and/or log file.

        Args:
            message: The message (can include Rich markup for console)
            style: Additional Rich style for console only
            use_prefix: Whether to include [co] prefix (default True)
        """
        # Build formatted message with [co] prefix
        if use_prefix:
            formatted = f"{_prefix()} {message}"
            plain = f"{_plain_prefix()} {self._to_plain_text(message)}"
        else:
            formatted = message
            plain = self._to_plain_text(message)

        # Print to terminal
        if style:
            _rich_console.print(formatted, style=style)
        else:
            _rich_console.print(formatted)

        # Log file output (plain text) if enabled
        if self.log_file:
            timestamp = datetime.now().strftime("%H:%M:%S")
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {plain}\n")

    def print_task(self, task: str) -> None:
        """Print the user's task/input.

        [co] > "find the latest AI papers"
        """
        # Truncate long tasks for display
        display_task = task[:100] + "..." if len(task) > 100 else task
        _rich_console.print()  # Empty line before
        self.print(f'> "{display_task}"')
        _rich_console.print()  # Empty line after

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

    def log_tool_call(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
        """Log tool call start - stores info for log_tool_result.

        [co]   ▸ search(query="AI papers")             ✓ 0.8s
        """
        # Store for later completion by log_tool_result
        self._current_tool = {
            'name': tool_name,
            'args': tool_args
        }

    def log_tool_result(self, result: str, timing_ms: float, success: bool = True) -> None:
        """Log tool completion with timing.

        [co]   ▸ search(query="AI papers")             ✓ 0.8s
        """
        tool_name = getattr(self, '_current_tool', {}).get('name', 'tool')
        tool_args = getattr(self, '_current_tool', {}).get('args', {})

        # Format tool call with smart truncation
        tool_str = self._format_tool_display(tool_name, tool_args)

        # Format timing
        time_str = f"{timing_ms/1000:.1f}s" if timing_ms >= 100 else f"{timing_ms/1000:.2f}s"

        # Build status indicator
        if success:
            status = f"[{SUCCESS_COLOR}]{SUCCESS_SYMBOL}[/{SUCCESS_COLOR}] [{DIM_COLOR}]{time_str}[/{DIM_COLOR}]"
        else:
            status = f"[{ERROR_COLOR}]{ERROR_SYMBOL}[/{ERROR_COLOR}] [{DIM_COLOR}]{time_str}[/{DIM_COLOR}]"

        # Right-align the status (target ~55 chars for tool part)
        # Green theme for tool action (triangle + tool name)
        tool_display = f"  [{TOOL_COLOR}]{TOOL_SYMBOL} {tool_str}[/{TOOL_COLOR}]"
        # Calculate padding (account for markup being removed in display)
        visible_len = len(f"  {TOOL_SYMBOL} {tool_str}")
        padding = max(1, 50 - visible_len)

        self.print(f"{tool_display}{' ' * padding}{status}")

    def _format_tool_display(self, name: str, args: Dict[str, Any], max_width: int = 45) -> str:
        """Format tool call with smart truncation.

        Rules:
        1. Max ~45 chars for tool display
        2. Show all param names when possible
        3. Use ... when truncation needed
        """
        if not args:
            return f"{name}()"

        # Calculate available space for args
        base_len = len(name) + 2  # name + ()
        available = max_width - base_len

        # Format each arg
        formatted = []
        for key, val in args.items():
            if isinstance(val, str):
                formatted.append((key, f'"{val}"'))
            else:
                formatted.append((key, str(val)))

        # Try to fit all args
        def build_args(items, max_val_len=None):
            parts = []
            for key, val in items:
                if max_val_len and len(val) > max_val_len:
                    val = val[:max_val_len-3] + '..."' if val.startswith('"') else val[:max_val_len-3] + "..."
                parts.append(f"{key}={val}")
            return ", ".join(parts)

        # First try: full values
        args_str = build_args(formatted)
        if len(args_str) <= available:
            return f"{name}({args_str})"

        # Second try: truncate values to 20 chars each
        args_str = build_args(formatted, max_val_len=20)
        if len(args_str) <= available:
            return f"{name}({args_str})"

        # Third try: truncate values to 10 chars each
        args_str = build_args(formatted, max_val_len=10)
        if len(args_str) <= available:
            return f"{name}({args_str})"

        # Last resort: first 2 args truncated + ...
        if len(formatted) > 2:
            args_str = build_args(formatted[:2], max_val_len=10) + ", ..."
        else:
            args_str = build_args(formatted, max_val_len=8)

        return f"{name}({args_str})"

    def print_llm_request(self, model: str, session: Dict[str, Any], max_iterations: int) -> None:
        """Print LLM request with violet empty circle (AI thinking).

        [co] ○ gemini-2.5-flash                              1/10

        Args:
            model: Model name
            session: Agent's current_session dict
            max_iterations: Agent's max_iterations setting
        """
        iteration = session.get('iteration', 1)

        # Build the line: violet circle, white model, dim metadata
        main_part = f"[{LLM_COLOR}]{CIRCLE_EMPTY}[/{LLM_COLOR}] {model}"
        meta_part = f"[{DIM_COLOR}]{iteration}/{max_iterations}[/{DIM_COLOR}]"

        # Right-align the iteration
        visible_len = len(f"{CIRCLE_EMPTY} {model}")
        padding = max(1, 50 - visible_len)

        self.print(f"{main_part}{' ' * padding}{meta_part}")

    def log_llm_response(self, model: str, duration_ms: float, tool_count: int, usage) -> None:
        """Log LLM response with violet filled circle (AI done thinking).

        [co] ● gemini-2.5-flash · 1 tools · 66 tok (42 cached) · $0.00   ✓ 1.8s

        Args:
            model: Model name
            duration_ms: Response time in milliseconds
            tool_count: Number of tool calls requested
            usage: TokenUsage object with input_tokens, output_tokens, cached_tokens, cost
        """
        # Format tokens with cache info
        total_tokens = usage.input_tokens + usage.output_tokens
        tokens_str = f"{total_tokens/1000:.1f}k tok" if total_tokens >= 1000 else f"{total_tokens} tok"
        cached = getattr(usage, 'cached_tokens', 0)
        if cached:
            tokens_str = f"{tokens_str} ({cached} cached)"

        # Format cost
        cost_str = f"${usage.cost:.4f}" if usage.cost < 0.01 else f"${usage.cost:.2f}"

        # Format timing
        time_str = f"{duration_ms/1000:.1f}s" if duration_ms >= 100 else f"{duration_ms/1000:.2f}s"

        # Build main part: violet circle, white model, white tools, dim metadata
        circle = f"[{LLM_COLOR}]{CIRCLE_FILLED}[/{LLM_COLOR}]"
        info_parts = [model]
        if tool_count:
            tool_word = "tool" if tool_count == 1 else "tools"
            info_parts.append(f"{tool_count} {tool_word}")
        info_parts.append(f"[{DIM_COLOR}]{tokens_str} · {cost_str}[/{DIM_COLOR}]")
        main_part = f"{circle} " + " · ".join(info_parts)

        # Build status: flash symbol for LLM completion, dim time
        status = f"[{LLM_COLOR}]{LLM_DONE_SYMBOL}[/{LLM_COLOR}] [{DIM_COLOR}]{time_str}[/{DIM_COLOR}]"

        # Calculate visible length for padding
        visible_text = f"{CIRCLE_FILLED} {model}"
        if tool_count:
            visible_text += f" · {tool_count} tools"
        visible_text += f" · {tokens_str} · {cost_str}"
        padding = max(1, 55 - len(visible_text))

        self.print(f"{main_part}{' ' * padding}{status}")

    def print_completion(
        self,
        duration_s: float,
        session: Dict[str, Any],
        session_path: Optional[str] = None
    ) -> None:
        """Print completion summary.

        [co] ═══════════════════════════════════════
        [co] ✓ done · 2.3k tokens · $0.005 · 3.4s
        [co]   saved → .co/sessions/research-assistant.yaml

        Args:
            duration_s: Total duration in seconds
            session: Agent's current_session dict (contains trace with usage)
            session_path: Optional path to session file
        """
        # Calculate totals from trace
        trace = session.get('trace', [])
        llm_calls = [t for t in trace if t.get('type') == 'llm_call']
        total_tokens = sum(
            (t.get('usage').input_tokens + t.get('usage').output_tokens)
            for t in llm_calls if t.get('usage')
        )
        total_cost = sum(
            t.get('usage').cost
            for t in llm_calls if t.get('usage')
        )

        # Format tokens
        tokens_str = f"{total_tokens/1000:.1f}k" if total_tokens >= 1000 else str(total_tokens)

        # Format cost
        cost_str = f"${total_cost:.4f}" if total_cost < 0.01 else f"${total_cost:.3f}"

        # Format time
        time_str = f"{duration_s:.1f}s"

        # Print separator
        _rich_console.print()
        self.print(f"[{DIM_COLOR}]═══════════════════════════════════════════════[/{DIM_COLOR}]")

        # Print summary: green check, white "complete", dim metadata
        self.print(f"[{SUCCESS_COLOR}]{SUCCESS_SYMBOL}[/{SUCCESS_COLOR}] complete [{DIM_COLOR}]· {tokens_str} tokens · {cost_str} · {time_str}[/{DIM_COLOR}]")

        # Print session path if provided (dim)
        if session_path:
            self.print(f"  [{DIM_COLOR}]{session_path}[/{DIM_COLOR}]")

        _rich_console.print()

    def _to_plain_text(self, message: str) -> str:
        """Convert Rich markup to plain text for log file."""
        # Remove Rich markup tags (matches anything in brackets: [bold cyan], [#FF0000], etc.)
        text = re.sub(r'\[[^\]]*\]', '', message)

        # Convert common symbols
        text = text.replace('→', '->')
        text = text.replace('←', '<-')
        text = text.replace('✓', '[OK]')
        text = text.replace('✗', '[ERROR]')

        return text