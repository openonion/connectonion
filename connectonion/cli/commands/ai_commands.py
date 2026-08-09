"""
Purpose: AI coding agent CLI command with concise provider-failure reporting
LLM-Note:
  Dependencies: imports from [cli/co_ai/main.py, cli/co_ai/agent.py] | imported by [cli/main.py] | no direct tests
  Data flow: CLI args → start_server() or agent.input() for one-shot
  Integration: exposes handle_ai() | called from main.py as 'co ai' command
  Errors: known LLM provider failures print one actionable message and exit 1; programmer errors still propagate with their traceback
"""

import typer
from rich.console import Console

console = Console()


def handle_ai(
    prompt: str = None,
    port: int = 8000,
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 100,
    yolo: bool = False,
    yolo_turns: int = 100,
):
    """Start AI coding agent or run one-shot prompt.

    Args:
        prompt: One-shot prompt (runs and exits)
        port: Port for web server
        model: LLM model to use
        max_iterations: Max tool iterations
        yolo: Skip tool approvals and keep working across turns
        yolo_turns: Maximum autonomous turns before a checkpoint

    Examples:
        co ai                                    # Start web server
        co ai "Create a calculator agent"        # One-shot
    """
    from ..co_ai.agent import GLOBAL_CO_DIR, create_agent
    agent = create_agent(
        model=model,
        max_iterations=max_iterations,
        co_dir=GLOBAL_CO_DIR,
        yolo_turns=yolo_turns if yolo else None,
    )

    if prompt:
        from ...core.exceptions import LLMProviderError
        try:
            result = agent.input(prompt)
        except LLMProviderError as exc:
            console.print(f"\n[red]✗ Model request failed:[/red] {exc}\n")
            raise typer.Exit(1) from None
        # Print the agent's response for one-shot mode
        print("\n" + result)
    else:
        from ..co_ai.main import start_server
        start_server(agent, port=port)
