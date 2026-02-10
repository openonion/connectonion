"""
Purpose: AI coding agent CLI command
LLM-Note:
  Dependencies: imports from [cli/co_ai/main.py, cli/co_ai/agent.py] | imported by [cli/main.py] | no direct tests
  Data flow: CLI args → start_server() or agent.input() for one-shot
  Integration: exposes handle_ai() | called from main.py as 'co ai' command
"""


def handle_ai(
    prompt: str = None,
    port: int = 8000,
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 20,
):
    """Start AI coding agent or run one-shot prompt.

    Args:
        prompt: One-shot prompt (runs and exits)
        port: Port for web server
        model: LLM model to use
        max_iterations: Max tool iterations

    Examples:
        co ai                                    # Start web server
        co ai "Create a calculator agent"        # One-shot
    """
    if prompt:
        from ..co_ai.agent import create_coding_agent
        agent = create_coding_agent(model=model, max_iterations=max_iterations)
        agent.input(prompt)
    else:
        from ..co_ai.main import start_server
        start_server(port=port, model=model, max_iterations=max_iterations)
