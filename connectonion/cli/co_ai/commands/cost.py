"""Cost command for showing session spending."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Module-level storage for agent reference
_current_agent = None


def set_agent(agent):
    """Set the current agent for cost tracking."""
    global _current_agent
    _current_agent = agent


def cmd_cost(args: str = "") -> str:
    """
    Display cost and token usage for the current session.

    Shows:
    - Total cost
    - Token usage (input/output)
    - Context usage percentage
    - Model being used
    """
    if _current_agent is None:
        console.print("[yellow]No agent session active. Start a conversation first.[/]")
        return "No session"

    agent = _current_agent

    # Build cost table
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value", style="cyan")

    # Model
    model = getattr(agent.llm, 'model', 'unknown')
    table.add_row("Model", model)

    # Cost
    total_cost = getattr(agent, 'total_cost', 0)
    if total_cost > 0:
        cost_str = f"${total_cost:.4f}" if total_cost < 0.01 else f"${total_cost:.2f}"
    else:
        cost_str = "$0.00"
    table.add_row("Total Cost", cost_str)

    # Token usage
    last_usage = getattr(agent, 'last_usage', None)
    if last_usage:
        input_tokens = last_usage.get('input_tokens', 0)
        output_tokens = last_usage.get('output_tokens', 0)
        table.add_row("Input Tokens", f"{input_tokens:,}")
        table.add_row("Output Tokens", f"{output_tokens:,}")
        table.add_row("Total Tokens", f"{input_tokens + output_tokens:,}")

    # Context usage
    context_percent = getattr(agent, 'context_percent', 0)
    if context_percent > 0:
        bar_width = 20
        filled = int(bar_width * context_percent / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        color = "green" if context_percent < 50 else "yellow" if context_percent < 80 else "red"
        table.add_row("Context Usage", f"[{color}]{bar}[/] {context_percent:.0f}%")

    # Messages count
    if hasattr(agent, 'current_session') and agent.current_session:
        messages = agent.current_session.get('messages', [])
        table.add_row("Messages", str(len(messages)))

    console.print(Panel(table, title="💰 Session Cost", border_style="green"))

    return f"Cost: {cost_str}"
