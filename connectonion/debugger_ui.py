"""
UI components for the interactive debugger.
This module handles all user interaction and display logic,
keeping it separate from the debugging orchestration.
"""

from typing import Any, Dict, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum
import json
import ast
import inspect

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

    def edit_value(self, current_value: Any) -> Tuple[bool, Any]:
        """Let user edit a value.

        Args:
            current_value: The current value to potentially edit

        Returns:
            Tuple of (was_changed, new_value)
        """
        self._display_current_value(current_value)

        if not self._confirm_edit():
            self.console.print("[green]Result unchanged[/green]")
            return False, current_value

        new_value = self._get_new_value()
        if new_value is not None:
            self._display_updated_value(new_value)
            return True, new_value
        else:
            self.console.print("[yellow]No changes made[/yellow]")
            return False, current_value

    # Private helper methods for cleaner code

    def _display_breakpoint_info(self, context: BreakpointContext) -> None:
        """Display complete debugging context from user prompt to execution result."""
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
                llm_branch.add(f"[bold yellow]⚡ {tool}() - {timing:.1f}ms ← PAUSED HERE[/bold yellow]")
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
                sections.append(Text(f"'{result}'", style="green"))
            elif isinstance(result, (dict, list)):
                try:
                    result_json = json.dumps(result, indent=2, ensure_ascii=False)
                    if len(result_json) > 200:
                        result_json = result_json[:200] + "..."
                    sections.append(Text(result_json, style="green"))
                except:
                    sections.append(Text(f"{str(result)[:100]}...", style="green"))
            else:
                sections.append(Text(str(result), style="green"))

        sections.append(Text(""))  # Spacing

        # Source code section
        sections.append(Text(f"Source (@xray at agent_debug.py:21)", style="dim italic"))

        source_code = self._get_tool_source(context.tool_name)
        if source_code:
            syntax = Syntax(source_code, "python", theme="monokai", line_numbers=True, line_range=(1, 10))
        else:
            # Fallback example
            fallback_code = """@xray
def search_info(query: str) -> str:
    \"\"\"Search for information.\"\"\"
    if "hello" in query.lower():
        return "Information about hello found..."
    return f"Information about '{query}' found in database.\""""
            syntax = Syntax(fallback_code, "python", theme="monokai", line_numbers=True)

        sections.append(syntax)
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
            f"Execution time: {timing:.1f}ms | Iteration: {context.iteration}/{context.max_iterations} | Breakpoint: @xray",
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

    def _get_tool_source(self, tool_name: str) -> Optional[str]:
        """Try to get the source code of a tool (simplified version)."""
        # This is a simplified version - in real implementation,
        # we'd need access to the actual tool object
        # For now, return None to use the example
        return None

    def _show_action_menu(self) -> BreakpointAction:
        """Show the action menu and get user's choice."""
        choices = [
            questionary.Choice("[c] Continue execution 🚀", value=BreakpointAction.CONTINUE, shortcut_key='c'),
            questionary.Choice("[e] Edit values 🔍", value=BreakpointAction.EDIT, shortcut_key='e'),
            questionary.Choice("[q] Quit debugging 🚫", value=BreakpointAction.QUIT, shortcut_key='q'),
        ]

        action = questionary.select(
            "\nAction:",
            choices=choices,
            style=self.style,
            instruction="(Use ↑/↓ arrows or press c/e/q + Enter)",
            use_shortcuts=True
        ).unsafe_ask()

        # Handle Ctrl+C
        if action is None:
            self.console.print("[yellow]→ Quitting debug session...[/yellow]")
            return BreakpointAction.QUIT

        if action == BreakpointAction.CONTINUE:
            self.console.print("[green]→ Continuing execution...[/green]")
        elif action == BreakpointAction.QUIT:
            self.console.print("[yellow]→ Quitting debug session...[/yellow]")

        return action

    def _display_current_value(self, value: Any) -> None:
        """Display the current value nicely formatted."""
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

    def _confirm_edit(self) -> bool:
        """Ask if user wants to edit the value."""
        return questionary.confirm(
            "Do you want to edit the result?",
            default=False
        ).ask()

    def _get_new_value(self) -> Optional[Any]:
        """Get new value from user."""
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
        """Display the updated value."""
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