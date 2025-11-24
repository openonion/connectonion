"""
Purpose: Provide Rich-formatted UI for interactive debugging with breakpoint display and user interaction
LLM-Note:
  Dependencies: imports from [typing, dataclasses, enum, json, ast, inspect, pprint, questionary, rich.*] | imported by [interactive_debugger.py] | no dedicated test file found
  Data flow: InteractiveDebugger creates DebuggerUI() → calls .show_welcome(agent_name) → .get_user_prompt() for input → .show_executing(prompt) → .show_breakpoint(context: BreakpointContext) → displays Rich panels/tables with tool execution details → returns BreakpointAction enum (CONTINUE, EDIT, WHY, QUIT) → .edit_value(context, agent) opens Python REPL for live modifications → returns modifications dict → .display_explanation(text, context) shows AI analysis
  State/Effects: no persistent state (stateless UI) | uses Rich Console to write formatted output to terminal | uses questionary for interactive menus | REPL execution in .edit_value() can have arbitrary side effects (user code) | does not modify agent or trace data directly (returns modifications)
  Integration: exposes DebuggerUI class, BreakpointContext dataclass, BreakpointAction enum | show_breakpoint() displays comprehensive debugging info: execution context, tool args/result, LLM next actions, source code, execution history | edit_value() provides REPL with access to trace_entry, tool_args, agent, result variables | display_explanation() formats AI-generated debugging insights
  Performance: Rich rendering is fast | source code inspection uses inspect.getsource() | execution history can be large (shows all tools) | REPL evaluation is synchronous (blocks UI)
  Errors: REPL errors caught and displayed with syntax highlighting | getsource() failures handled gracefully (shows "unavailable") | questionary keyboard interrupts propagate up | assumes terminal supports Rich formatting
"""

from typing import Any, Dict, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum
import json
import ast
import inspect
from pprint import pformat

import questionary
from questionary import Style
from rich.console import Console as RichConsole
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree
from rich import box


class BreakpointAction(Enum):
    """User's choice at a breakpoint"""
    CONTINUE = "continue"
    EDIT = "edit"
    WHY = "why"
    QUIT = "quit"


@dataclass
class BreakpointContext:
    """All data needed to display a breakpoint"""
    tool_name: str
    tool_args: Dict
    trace_entry: Dict
    user_prompt: str
    iteration: int
    max_iterations: int
    previous_tools: List[str]
    next_actions: Optional[List[Dict]] = None  # Preview of next planned tools
    tool_function: Optional[Any] = None  # The actual tool function for source inspection


class DebuggerUI:
    """Handles all user interaction and display for the debugger."""

    def __init__(self):
        """Initialize the UI with styling."""
        self.console = RichConsole()
        self.style = Style([
            ('question', 'fg:#00ffff bold'),
            ('pointer', 'fg:#00ff00 bold'),
            ('highlighted', 'fg:#00ff00 bold'),
            ('selected', 'fg:#00ffff'),
            ('instruction', 'fg:#808080'),
        ])

    def show_welcome(self, agent_name: str) -> None:
        """Display welcome panel for debug session.

        Args:
            agent_name: Name of the agent being debugged
        """
        self.console.print(Panel(
            "[bold cyan]🔍 Interactive Debug Session Started[/bold cyan]\n\n"
            f"Agent: [yellow]{agent_name}[/yellow]\n"
            "Tools with @xray will pause for inspection\n"
            "Interactive menu at breakpoints to continue or edit\n",
            title="Auto Debug",
            border_style="cyan"
        ))

    def get_user_prompt(self) -> Optional[str]:
        """Get prompt from user or None if they want to quit.

        Returns:
            User's prompt string or None to quit
        """
        prompt = input("\nEnter prompt for agent (or 'quit' to exit): ").strip()

        if prompt.lower() in ['quit', 'exit', 'q']:
            self.console.print("[yellow]Debug session ended.[/yellow]")
            return None

        return prompt if prompt else self.get_user_prompt()  # Retry if empty

    def show_executing(self, prompt: str) -> None:
        """Show that a prompt is being executed.

        Args:
            prompt: The prompt being executed
        """
        self.console.print(f"\n[cyan]→ Executing: {prompt}[/cyan]")

    def show_result(self, result: str) -> None:
        """Display the final result of task execution.

        Args:
            result: The result to display
        """
        self.console.print(f"\n[green]✓ Result:[/green] {result}")

    def show_interrupted(self) -> None:
        """Show that task was interrupted."""
        self.console.print("\n[yellow]Task interrupted.[/yellow]")

    def show_breakpoint(self, context: BreakpointContext) -> BreakpointAction:
        """Display breakpoint UI and get user's choice.

        Shows tool information, arguments, results, and a menu
        for the user to choose their action.

        Args:
            context: All context data for the breakpoint

        Returns:
            User's chosen action
        """
        self._display_breakpoint_info(context)
        return self._show_action_menu()

    def edit_value(self, context: BreakpointContext, agent: Any = None) -> Dict[str, Any]:
        """Start Python REPL to inspect and modify execution state.

        Args:
            context: Full breakpoint context with all execution data
            agent: Optional agent instance for accessing agent context

        Returns:
            Dict of modified values (e.g., {'result': new_value, 'tool_args': {...}})
        """
        import code

        # Build namespace with all debuggable variables
        result = context.trace_entry.get('result')
        namespace = {
            # Primary execution
            'result': result,
            'tool_name': context.tool_name,
            'tool_args': context.tool_args.copy(),  # Make it mutable

            # Flow control
            'iteration': context.iteration,
            'max_iterations': context.max_iterations,

            # Context
            'user_prompt': context.user_prompt,
            'next_actions': context.next_actions,

            # Advanced
            'trace_entry': context.trace_entry,
            'previous_tools': context.previous_tools,
        }

        # Add agent context if available
        if agent:
            namespace.update({
                'agent_name': agent.name,
                'model': agent.llm.model if hasattr(agent.llm, 'model') else 'unknown',
                'tools_available': [tool.name for tool in agent.tools] if agent.tools else [],
                'turn': agent.current_session.get('turn', 0) if agent.current_session else 0,
                'messages': agent.current_session.get('messages', []) if agent.current_session else [],
            })

        # Add helper function for pretty printing in REPL
        def pp(obj):
            """Pretty print helper for explicit use"""
            from rich.pretty import pprint
            pprint(obj, expand_all=True)

        namespace['pp'] = pp  # Add to namespace

        # Display REPL header
        self._display_repl_header(context, namespace)

        # Customize REPL display hook to auto pretty-print
        import sys
        from rich.pretty import pprint

        original_displayhook = sys.displayhook

        def rich_displayhook(value):
            """Custom display hook that uses Rich pretty printing"""
            if value is not None:
                pprint(value, expand_all=True)
                # Also store in _ for REPL access
                import builtins
                builtins._ = value

        sys.displayhook = rich_displayhook

        # Check if stdin is available for interactive REPL
        if not sys.stdin or not hasattr(sys.stdin, 'isatty') or not sys.stdin.isatty():
            self.console.print("\n[yellow]⚠️  Interactive REPL not available (stdin not connected)[/yellow]")
            self.console.print("[dim]Tip: Run directly in a terminal (not through VSCode/IDE) to use EDIT feature[/dim]")
            return {}

        # Start interactive Python REPL
        banner = ""  # Empty banner since we show our own header
        try:
            code.interact(banner=banner, local=namespace, exitmsg="")
        except SystemExit:
            pass  # Normal REPL exit
        finally:
            # Restore original displayhook
            sys.displayhook = original_displayhook

        # Extract modifications from namespace
        modifications = {}
        if namespace['result'] != result:
            modifications['result'] = namespace['result']
        if namespace['tool_args'] != context.tool_args:
            modifications['tool_args'] = namespace['tool_args']
        if namespace['iteration'] != context.iteration:
            modifications['iteration'] = namespace['iteration']
        if namespace['max_iterations'] != context.max_iterations:
            modifications['max_iterations'] = namespace['max_iterations']

        # Show what was modified
        if modifications:
            self._display_modifications(modifications)
        else:
            self.console.print("\n[dim]No modifications made[/dim]")

        return modifications

    # Private helper methods for cleaner code

    def _display_breakpoint_info(self, context: BreakpointContext) -> None:
        """Display complete debugging context from user prompt to execution result.

        Shows a comprehensive panel with:
        - User prompt and iteration context
        - Execution flow tree (previous → current → next tools)
        - Current execution details (function call, result, source code)
        - Next planned action preview

        Args:
            context: All breakpoint data including tool info, execution state, and previews
        """
        # Clear some space
        self.console.print("\n")

        # Build sections without individual panels
        sections = []

        # 1. Context Section
        prompt_display = context.user_prompt if len(context.user_prompt) <= 80 else f"{context.user_prompt[:80]}..."
        sections.append(Text("CONTEXT", style="bold dim"))
        sections.append(Text(f'User Prompt: "{prompt_display}"', style="cyan"))
        sections.append(Text(f"Iteration: {context.iteration}/{context.max_iterations} | Model: o4-mini", style="dim"))
        sections.append(Text(""))  # Empty line for spacing

        # 2. Execution Flow Section
        sections.append(Text("EXECUTION FLOW", style="bold dim"))

        tree = Tree("User Input")
        llm_branch = tree.add("LLM Decision")

        # Add all tools in the chain
        all_tools = context.previous_tools + [context.tool_name]
        for i, tool in enumerate(all_tools):
            if tool == context.tool_name:
                # Current tool (highlighted)
                timing = context.trace_entry.get('timing', 0)
                llm_branch.add(f"[bold yellow]⚡ {tool}() - {timing/1000:.4f}s ← PAUSED HERE[/bold yellow]")
            elif i < len(context.previous_tools):
                # Completed tools
                llm_branch.add(f"✓ {tool}() - [dim]completed[/dim]")

        # Add next planned actions based on LLM preview
        if context.next_actions is not None:
            if context.next_actions:
                # Show the actual planned next tools
                for i, action in enumerate(context.next_actions):
                    tool_name = action['name']
                    tool_args = action.get('args', {})

                    # Format arguments for display
                    args_display = []
                    for key, value in tool_args.items():
                        if isinstance(value, str) and len(value) > 20:
                            args_display.append(f"{key}='...'")
                        elif isinstance(value, str):
                            args_display.append(f"{key}='{value}'")
                        else:
                            args_display.append(f"{key}={value}")
                    args_str = ', '.join(args_display) if args_display else ''

                    llm_branch.add(f"📍 {tool_name}({args_str}) - [dim]planned next[/dim]")
            else:
                # No more tools planned - task complete
                llm_branch.add("✅ Task complete - [dim]no more tools needed[/dim]")
        else:
            # Preview unavailable (error or couldn't determine)
            llm_branch.add("❓ Next action - [dim]preview unavailable[/dim]")

        sections.append(tree)
        sections.append(Text(""))  # Empty line for spacing

        # 3. Current Execution Section (the main focus)
        sections.append(Text("─" * 60, style="dim"))  # Visual separator
        sections.append(Text("CURRENT EXECUTION", style="bold yellow"))
        sections.append(Text(""))

        # Build the function call
        args_str_parts = []
        if context.tool_args:
            for key, value in context.tool_args.items():
                if isinstance(value, str):
                    args_str_parts.append(f'{key}="{value}"')
                else:
                    args_str_parts.append(f'{key}={value}')
        function_call = f"{context.tool_name}({', '.join(args_str_parts)})"

        # Get the result
        result = context.trace_entry.get('result', 'No result')
        is_error = context.trace_entry.get('status') == 'error'

        # REPL section
        sections.append(Text(f">>> {function_call}", style="bold bright_cyan"))

        if is_error:
            error = context.trace_entry.get('error', str(result))
            sections.append(Text(f"Error: {error}", style="red"))
        else:
            if isinstance(result, str):
                display_result = result[:150] + ('...' if len(result) > 150 else '')
                sections.append(Text(f"'{display_result}'", style="green"))
            elif isinstance(result, (dict, list)):
                try:
                    result_json = json.dumps(result, indent=2, ensure_ascii=False)
                    display_json = result_json[:200] + ('...' if len(result_json) > 200 else '')
                    sections.append(Text(display_json, style="green"))
                except:
                    sections.append(Text(f"{str(result)[:100]}...", style="green"))
            else:
                sections.append(Text(str(result), style="green"))

        sections.append(Text(""))  # Spacing

        # Source code section
        source_code, file_info, start_line = self._get_tool_source(context)
        sections.append(Text(f"Source ({file_info})", style="dim italic"))

        if source_code:
            # Use start_line_number to show actual file line numbers
            syntax = Syntax(
                source_code,
                "python",
                theme="monokai",
                line_numbers=True,
                start_line=start_line
            )
            sections.append(syntax)
        else:
            sections.append(Text("  Source code unavailable", style="dim"))
        sections.append(Text("─" * 60, style="dim"))  # Visual separator
        sections.append(Text(""))  # Spacing

        # 4. Next Planned Action Section
        sections.append(Text("NEXT PLANNED ACTION", style="bold dim"))

        if context.next_actions is not None:
            if context.next_actions:
                # Show what LLM plans to do next
                sections.append(Text("The LLM will call:", style="dim"))

                for action in context.next_actions[:1]:  # Show just the first one in detail
                    tool_name = action['name']
                    tool_args = action.get('args', {})

                    # Format the planned call
                    args_parts = []
                    for key, value in tool_args.items():
                        if isinstance(value, str):
                            # Show more of the string here since it's a preview
                            if len(value) > 50:
                                args_parts.append(f'{key}="{value[:50]}..."')
                            else:
                                args_parts.append(f'{key}="{value}"')
                        else:
                            args_parts.append(f'{key}={value}')

                    planned_call = f"{tool_name}({', '.join(args_parts)})"
                    sections.append(Text(planned_call, style="cyan bold"))

                if len(context.next_actions) > 1:
                    sections.append(Text(f"(and {len(context.next_actions) - 1} more planned actions)", style="dim"))
            else:
                # Task complete
                sections.append(Text("🎯 Task Complete", style="bold green"))
                sections.append(Text("No further tools needed", style="green"))
        else:
            # Preview unavailable
            sections.append(Text("Preview temporarily unavailable", style="dim italic"))

        # 5. Add metadata footer
        sections.append(Text(""))  # Spacing
        timing = context.trace_entry.get('timing', 0)
        metadata = Text(
            f"Execution time: {timing/1000:.4f}s | Iteration: {context.iteration}/{context.max_iterations} | Breakpoint: @xray",
            style="dim italic",
            justify="center"
        )
        sections.append(metadata)

        # 6. Combine everything into a single panel with proper spacing
        all_content = Group(*sections)

        # 7. Create single main wrapper panel
        if is_error:
            title = "⚠️  Execution Paused - Error"
            border_style = "red"
        else:
            title = "🔍 Execution Paused - Breakpoint"
            border_style = "yellow"

        main_panel = Panel(
            all_content,
            title=f"[bold {border_style}]{title}[/bold {border_style}]",
            box=box.ROUNDED,
            border_style=border_style,
            padding=(1, 2)
        )

        self.console.print(main_panel)

    def _get_tool_source(self, context: BreakpointContext) -> Tuple[Optional[str], str, int]:
        """Get the source code of the actual tool function.

        Unwraps decorators to get the original function and extracts:
        - Source code using inspect.getsource()
        - File location and starting line number
        - File info formatted as "filename:line"

        Args:
            context: Breakpoint context containing tool_function

        Returns:
            Tuple of (source_code, file_info, start_line_number)
            Returns (None, "source unavailable", 1) if function not available
        """
        if not context.tool_function:
            return None, "source unavailable", 1

        # Unwrap to get the original function (not the wrapper)
        func = context.tool_function
        while hasattr(func, '__wrapped__'):
            func = func.__wrapped__

        source = inspect.getsource(func)
        file_path = inspect.getfile(func)
        start_line = inspect.getsourcelines(func)[1]

        # Show just filename:line
        import os
        file_name = os.path.basename(file_path)
        file_info = f"{file_name}:{start_line}"

        return source, file_info, start_line

    def _show_action_menu(self) -> BreakpointAction:
        """Show the action menu and get user's choice.

        Tries multiple UI libraries in order of preference:
        1. simple-term-menu (best compatibility, no asyncio conflicts)
        2. questionary (may conflict with Playwright/asyncio)
        3. simple input fallback (when no TTY or event loop conflicts)

        Returns:
            User's chosen action (CONTINUE, EDIT, or QUIT)
        """
        # Try to use simple-term-menu (no asyncio conflicts, works with Playwright)
        try:
            from simple_term_menu import TerminalMenu

            menu_entries = [
                "[c] Continue execution 🚀",
                "[e] Edit values 🔍",
                "[w] Why this tool? 🤔",
                "[q] Quit debugging 🚫"
            ]

            terminal_menu = TerminalMenu(
                menu_entries,
                title="\nAction:",
                menu_cursor="→ ",
                menu_cursor_style=("fg_green", "bold"),
                menu_highlight_style=("fg_green", "bold"),
                cycle_cursor=True,
                clear_screen=False,
            )

            menu_index = terminal_menu.show()

            # Handle Ctrl+C or None
            if menu_index is None:
                self.console.print("[yellow]→ Quitting debug session...[/yellow]")
                return BreakpointAction.QUIT

            # Map index to action
            actions = [BreakpointAction.CONTINUE, BreakpointAction.EDIT, BreakpointAction.WHY, BreakpointAction.QUIT]
            action = actions[menu_index]

            if action == BreakpointAction.CONTINUE:
                self.console.print("[green]→ Continuing execution...[/green]")
            elif action == BreakpointAction.WHY:
                self.console.print("[cyan]→ Analyzing why tool was chosen...[/cyan]")
            elif action == BreakpointAction.QUIT:
                self.console.print("[yellow]→ Quitting debug session...[/yellow]")

            return action

        except (ImportError, OSError):
            # simple-term-menu not installed, not supported (Windows), or no TTY available
            # Fall back to questionary or simple input
            pass

        # Fallback: Use questionary (may have asyncio conflicts with Playwright)
        choices = [
            questionary.Choice("[c] Continue execution 🚀", value=BreakpointAction.CONTINUE, shortcut_key='c'),
            questionary.Choice("[e] Edit values 🔍", value=BreakpointAction.EDIT, shortcut_key='e'),
            questionary.Choice("[w] Why this tool? 🤔", value=BreakpointAction.WHY, shortcut_key='w'),
            questionary.Choice("[q] Quit debugging 🚫", value=BreakpointAction.QUIT, shortcut_key='q'),
        ]

        try:
            action = questionary.select(
                "\nAction:",
                choices=choices,
                style=self.style,
                instruction="(Press c/e/w/q)",
                use_shortcuts=True,
                use_indicator=False,
                use_arrow_keys=True
            ).ask()
        except RuntimeError:
            # Event loop conflict - use simple input fallback
            return self._simple_input_fallback()

        # Handle Ctrl+C
        if action is None:
            self.console.print("[yellow]→ Quitting debug session...[/yellow]")
            return BreakpointAction.QUIT

        if action == BreakpointAction.CONTINUE:
            self.console.print("[green]→ Continuing execution...[/green]")
        elif action == BreakpointAction.WHY:
            self.console.print("[cyan]→ Analyzing why tool was chosen...[/cyan]")
        elif action == BreakpointAction.QUIT:
            self.console.print("[yellow]→ Quitting debug session...[/yellow]")

        return action

    def _simple_input_fallback(self) -> BreakpointAction:
        """Simple text input fallback when event loop conflicts occur.

        Used when:
        - Asyncio event loop is already running (Playwright, Jupyter)
        - No TTY available
        - Menu libraries not installed or not supported

        Returns:
            User's chosen action based on keyboard input (c/e/w/q)
        """
        self.console.print("\n[cyan bold]Action:[/cyan bold]")
        self.console.print("  [c] Continue execution 🚀")
        self.console.print("  [e] Edit values 🔍")
        self.console.print("  [w] Why this tool? 🤔")
        self.console.print("  [q] Quit debugging 🚫")

        while True:
            try:
                choice = input("\nYour choice (c/e/w/q): ").strip().lower()
                if choice == 'c':
                    self.console.print("[green]→ Continuing execution...[/green]")
                    return BreakpointAction.CONTINUE
                elif choice == 'e':
                    return BreakpointAction.EDIT
                elif choice == 'w':
                    self.console.print("[cyan]→ Analyzing why tool was chosen...[/cyan]")
                    return BreakpointAction.WHY
                elif choice == 'q':
                    self.console.print("[yellow]→ Quitting debug session...[/yellow]")
                    return BreakpointAction.QUIT
                else:
                    self.console.print("[yellow]Invalid choice. Please enter c, e, w, or q.[/yellow]")
            except (KeyboardInterrupt, EOFError):
                self.console.print("\n[yellow]→ Quitting debug session...[/yellow]")
                return BreakpointAction.QUIT

    def _display_current_value(self, value: Any) -> None:
        """Display the current value nicely formatted.

        Uses Rich syntax highlighting for JSON and appropriate
        formatting for strings, dicts, lists, and other types.

        Args:
            value: The value to display (any type)
        """
        self.console.print("\n")

        # Create a table for the value display
        value_table = Table(show_header=False, box=None)
        value_table.add_column()

        # Format value based on type
        if isinstance(value, (dict, list)):
            try:
                json_str = json.dumps(value, indent=2, ensure_ascii=False)
                # Use syntax highlighting for JSON
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
                value_table.add_row(syntax)
            except:
                value_table.add_row(f"[green]{value}[/green]")
        elif isinstance(value, str):
            # For strings, show with quotes
            if len(value) > 500:
                value_table.add_row(f'[green]"{value[:500]}..."[/green]')
            else:
                value_table.add_row(f'[green]"{value}"[/green]')
        else:
            value_table.add_row(f"[green]{value}[/green]")

        # Display in a panel
        panel = Panel(
            value_table,
            title="[bold cyan]📝 Current Result[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        )
        self.console.print(panel)

    def _get_new_value(self) -> Optional[Any]:
        """Get new value from user via text input.

        Prompts user to enter a Python expression and attempts to
        parse it using ast.literal_eval(). Falls back to treating
        as string if parsing fails.

        Returns:
            Parsed Python value (str, dict, list, etc.) or None if empty
        """
        self.console.print("\n[cyan]Enter new result value:[/cyan]")
        self.console.print("[dim]Tip: Enter valid Python expression (string, dict, list, etc.)[/dim]")
        self.console.print("[dim]Examples: 'new text', {'key': 'value'}, [1, 2, 3][/dim]\n")

        new_value_str = input("New result: ").strip()

        if not new_value_str:
            return None

        try:
            # Try to evaluate as Python expression
            return ast.literal_eval(new_value_str)
        except (ValueError, SyntaxError):
            # If not valid Python literal, treat as string
            return new_value_str

    def _display_updated_value(self, value: Any) -> None:
        """Display the updated value after successful modification.

        Shows success message and formatted value in yellow panel
        to distinguish from the original value display.

        Args:
            value: The newly updated value to display
        """
        self.console.print(f"\n[green]✅ Result updated successfully![/green]\n")

        # Create a table for the updated value
        value_table = Table(show_header=False, box=None)
        value_table.add_column()

        # Format value based on type
        if isinstance(value, (dict, list)):
            try:
                json_str = json.dumps(value, indent=2, ensure_ascii=False)
                # Use syntax highlighting
                syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
                value_table.add_row(syntax)
            except:
                value_table.add_row(f"[yellow]{value}[/yellow]")
        elif isinstance(value, str):
            if len(value) > 500:
                value_table.add_row(f'[yellow]"{value[:500]}..."[/yellow]')
            else:
                value_table.add_row(f'[yellow]"{value}"[/yellow]')
        else:
            value_table.add_row(f"[yellow]{value}[/yellow]")

        # Display in a panel with different style
        panel = Panel(
            value_table,
            title="[bold yellow]✨ Updated Result[/bold yellow]",
            border_style="yellow",
            padding=(1, 2)
        )
        self.console.print(panel)
    def _display_repl_header(self, context: BreakpointContext, namespace: Dict[str, Any]) -> None:
        """Display Python REPL header with available variables.

        Shows a clean table of all variables available in the REPL namespace,
        organized by priority groups:
        1. Execution: result, tool_name, tool_args
        2. Control: iteration, max_iterations
        3. Context: user_prompt, next_actions
        4. Agent: agent_name, model, turn, tools_available
        5. Advanced: messages, trace_entry, previous_tools
        6. Helpers: pp (pretty print function)

        Args:
            context: Breakpoint context for reference
            namespace: Dict of all variables available in REPL
        """
        self.console.print("\n")
        self.console.print(Panel(
            "[bold white]Python REPL - Interactive Debugging[/bold white]\n"
            "[dim]Modify any variable and exit() to apply changes[/dim]",
            title="🐍 Debug Console",
            border_style="green"
        ))

        # Create clean two-column table
        table = Table(
            show_header=True,
            header_style="bold cyan",
            border_style="dim",
            box=box.SIMPLE_HEAD,  # Only header has border
            padding=(0, 2),  # 0 vertical, 2 horizontal
            show_lines=False
        )

        # Two columns: Variable (fixed) and Value (flexible)
        table.add_column("Variable", style="yellow", width=18, no_wrap=True)
        table.add_column("Value", style="white", overflow="fold")

        # Priority ordering for smart grouping
        priority_order = [
            'result', 'tool_name', 'tool_args',               # Group 1: Execution
            'iteration', 'max_iterations',                     # Group 2: Control
            'user_prompt', 'next_actions',                     # Group 3: Context
            'agent_name', 'model', 'turn', 'tools_available',  # Group 4: Agent
            'messages', 'trace_entry', 'previous_tools',       # Group 5: Advanced
            'pp',                                              # Group 6: Helper (show last)
        ]

        # Sort variables by priority
        sorted_items = []
        for key in priority_order:
            if key in namespace:
                sorted_items.append((key, namespace[key]))

        # Add any remaining variables not in priority list
        for key, value in namespace.items():
            if key not in priority_order:
                sorted_items.append((key, value))

        # Add rows with automatic grouping
        group_breaks = [2, 4, 6, 10]  # Add empty row after these indices (Execution, Control, Context, Agent, Advanced)

        for i, (var_name, var_value) in enumerate(sorted_items):
            # Add empty row for visual grouping
            if i in group_breaks:
                table.add_row("", "")

            # Format value with smart formatting
            formatted_value = self._format_value_for_repl(var_value)
            table.add_row(var_name, formatted_value)

        self.console.print(table)
        self.console.print()

    def _format_value_for_repl(self, value: Any) -> str:
        """Format value with smart, consistent formatting for REPL display.

        Handles different types intelligently:
        - None/bools/numbers: Compact cyan format
        - Strings: Truncate with char count if > 80 chars
        - Dicts: Inline if small, indented if medium, collapsed if large
        - Lists: Inline if simple, indented if fits, collapsed if large
        - Functions: Show as helper description

        Args:
            value: Any Python value to format

        Returns:
            Rich-formatted string for display in REPL table
        """

        # None
        if value is None:
            return "[dim]None[/dim]"

        # Booleans
        elif isinstance(value, bool):
            return f"[cyan]{value}[/cyan]"

        # Numbers
        elif isinstance(value, (int, float)):
            return f"[cyan]{value}[/cyan]"

        # Strings
        elif isinstance(value, str):
            return self._format_string_value(value)

        # Dictionaries
        elif isinstance(value, dict):
            return self._format_dict_value(value)

        # Lists
        elif isinstance(value, list):
            return self._format_list_value(value)

        # Functions (like pp helper)
        elif callable(value):
            return f"[dim]<function>[/dim] [dim italic]- helper for pretty printing[/dim italic]"

        # Other types - just show string representation
        else:
            str_repr = str(value)
            if len(str_repr) <= 100:
                return f"[white]{str_repr}[/white]"
            else:
                return f"[white]{str_repr[:100]}...[/white] [dim]({len(str_repr)} chars)[/dim]"

    def _format_string_value(self, s: str) -> str:
        """Format string values with truncation and char count.

        Args:
            s: String to format

        Returns:
            Short strings (≤80 chars): repr() with green color
            Long strings (>80 chars): Truncated with "..." and char count
        """
        # Short strings - show as-is
        if len(s) <= 80:
            return f"[green]{repr(s)}[/green]"

        # Long strings - truncate and show char count
        truncated = repr(s[:80])[:-1] + "...'"  # Remove closing quote, add ellipsis
        return f"[green]{truncated}[/green]\n                    [dim]({len(s)} chars)[/dim]"

    def _format_dict_value(self, d: dict) -> str:
        """Format dict values using pprint for clean output.

        Args:
            d: Dictionary to format

        Returns:
            Empty dict: "{{}}" in dim
            Small dict (≤3 keys, fits inline): Compact cyan format
            Medium dict (≤5 lines): Multi-line with indentation
            Large dict: Collapsed summary with key count and pp() hint
        """
        if not d:
            return "[dim]{{}}[/dim]"

        # Use pprint for nice formatting
        pp = pformat(d, width=60, depth=2, compact=True)
        lines = pp.split('\n')

        # Small dict - show inline
        if len(d) <= 3 and len(lines) == 1 and len(pp) <= 60:
            return f"[cyan]{pp}[/cyan]"

        # Medium dict - show with indentation
        if len(lines) <= 5:
            formatted_lines = [lines[0]]
            for line in lines[1:]:
                formatted_lines.append(f"                    {line}")
            return f"[cyan]{chr(10).join(formatted_lines)}[/cyan]"

        # Large dict - collapse with summary
        return f"[dim cyan]{{... {len(d)} keys}}[/dim cyan] [dim]- type: pp(var_name)[/dim]"

    def _format_list_value(self, lst: list) -> str:
        """Format list values using pprint for clean output.

        Args:
            lst: List to format

        Returns:
            Empty list: "[]" in dim
            Simple string list (≤5 items, fits inline): Compact format
            Medium list (≤5 lines): Multi-line with indentation
            Large list: Collapsed summary with item count and pp() hint
        """
        if not lst:
            return "[dim][][/dim]"

        # Simple list of strings - show inline
        if all(isinstance(item, str) for item in lst) and len(lst) <= 5:
            compact = "[" + ", ".join(f'"{s}"' for s in lst) + "]"
            if len(compact) <= 60:
                return f"[cyan]{compact}[/cyan]"

        # Use pprint for nice formatting
        pp = pformat(lst, width=60, depth=2, compact=True)
        lines = pp.split('\n')

        # If fits in a few lines, show it
        if len(lines) <= 5:
            formatted_lines = [lines[0]]
            for line in lines[1:]:
                formatted_lines.append(f"                    {line}")
            result = chr(10).join(formatted_lines)
            return f"[cyan]{result}[/cyan]"

        # Large - show summary with hint
        return f"[dim cyan][... {len(lst)} items][/dim cyan] [dim]- type: pp(var_name)[/dim]"

    def _format_value_preview(self, value: Any) -> str:
        """Format a value for compact preview display.

        Used for showing values in constrained spaces like next action previews.

        Args:
            value: Any value to format

        Returns:
            Truncated string representation (max 30 chars)
        """
        if isinstance(value, str):
            return f"'{value[:30]}...'" if len(value) > 30 else f"'{value}'"
        elif isinstance(value, (dict, list)):
            val_str = str(value)
            return f"{val_str[:30]}..." if len(val_str) > 30 else val_str
        else:
            return str(value)

    def _display_modifications(self, modifications: Dict[str, Any]) -> None:
        """Display what was modified during REPL session.

        Shows each modified variable with its new value,
        formatted appropriately for display.

        Args:
            modifications: Dict of variable_name -> new_value pairs
        """
        self.console.print("\n[bold green]✅ Modifications Applied:[/bold green]\n")
        
        for key, value in modifications.items():
            # Format the value for display
            if isinstance(value, str):
                formatted = f"'{value}'" if len(value) <= 50 else f"'{value[:50]}...'"
            elif isinstance(value, dict):
                formatted = json.dumps(value, indent=2)[:100]
            else:
                formatted = str(value)
            
            self.console.print(f"  [yellow]{key}[/yellow] = [cyan]{formatted}[/cyan]")

        self.console.print()

    def display_explanation(self, explanation: str, context: BreakpointContext) -> None:
        """Display AI explanation of why a tool was chosen.

        Args:
            explanation: The explanation text from the AI
            context: Breakpoint context for displaying relevant info
        """
        self.console.print("\n")

        panel = Panel(
            explanation,
            title=f"[bold cyan]🤔 Why {context.tool_name}?[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        )

        self.console.print(panel)
        self.console.print()

        input("[dim]Press Enter to return to menu...[/dim]")

    def display_execution_analysis(self, analysis) -> None:
        """Display post-execution analysis with improvement suggestions.

        Args:
            analysis: ExecutionAnalysis object with structured results
        """
        self.console.print("\n")
        self.console.print("[bold cyan]═══ 📊 Execution Analysis ═══[/bold cyan]\n")

        # Task completion status
        status_emoji = "✅" if analysis.task_completed else "❌"
        self.console.print(f"{status_emoji} [bold]Task Completed:[/bold] {analysis.task_completed}")
        self.console.print(f"   {analysis.completion_explanation}\n")

        # Overall quality
        quality_colors = {
            "excellent": "green",
            "good": "cyan",
            "fair": "yellow",
            "poor": "red"
        }
        quality_color = quality_colors.get(analysis.overall_quality, "white")
        self.console.print(f"[bold]Quality:[/bold] [{quality_color}]{analysis.overall_quality.upper()}[/{quality_color}]\n")

        # Problems identified
        if analysis.problems_identified:
            self.console.print("[bold red]⚠️  Problems Identified:[/bold red]")
            for i, problem in enumerate(analysis.problems_identified, 1):
                self.console.print(f"   {i}. {problem}")
            self.console.print()

        # System prompt suggestions
        if analysis.system_prompt_suggestions:
            panel = Panel(
                "\n".join(f"• {suggestion}" for suggestion in analysis.system_prompt_suggestions),
                title="[bold green]💡 System Prompt Suggestions[/bold green]",
                border_style="green",
                padding=(1, 2)
            )
            self.console.print(panel)
            self.console.print()

        # Key insights
        if analysis.key_insights:
            self.console.print("[bold magenta]🎯 Key Insights:[/bold magenta]")
            for i, insight in enumerate(analysis.key_insights, 1):
                self.console.print(f"   {i}. {insight}")
            self.console.print()

        self.console.print("[dim]" + "═" * 60 + "[/dim]\n")
        input("[dim]Press Enter to continue...[/dim]")
