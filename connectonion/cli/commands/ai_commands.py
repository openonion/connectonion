"""
Purpose: AI coding agent CLI command
LLM-Note:
  Dependencies: imports from [cli/co_ai/main.py] | imported by [cli/main.py] | no direct tests
  Data flow: CLI args → start_server(port, model, max_iterations) → co_ai.main.start_server()
  Integration: exposes handle_ai() | called from main.py as 'co ai' command
"""

from rich.console import Console

console = Console()


def handle_ai(
    port: int = 8000,
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 20,
):
    """Start AI coding agent web server.

    Args:
        port: Port to run server on
        model: LLM model to use
        max_iterations: Max tool calling iterations

    Examples:
        co ai                      # Start on port 8000
        co ai --port 3001          # Custom port
        co ai --model co/gpt-5     # Different model
    """
    from ..co_ai.main import start_server

    # Server startup banner is printed by host() - no duplicate message needed
    start_server(port=port, model=model, max_iterations=max_iterations)
