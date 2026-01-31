"""AI coding agent web server entry point."""

import logging
from pathlib import Path
from dotenv import load_dotenv
from connectonion import host

logging.basicConfig(
    level=logging.WARNING,
    format='[%(levelname)s] %(name)s: %(message)s'
)


# Load global keys.env for CLI commands (fallback for API keys)
# Priority: current directory .env > global ~/.co/keys.env
_global_keys = Path.home() / ".co" / "keys.env"
if _global_keys.exists():
    # load_dotenv doesn't override existing env vars, so cwd .env takes priority
    load_dotenv(_global_keys)


def start_server(
    port: int = 8000,
    model: str = "co/claude-opus-4-5",
    max_iterations: int = 20,
):
    """Start AI coding agent web server.

    Args:
        port: Port to run server on
        model: LLM model to use
        max_iterations: Max tool iterations

    The server will be accessible at:
    - POST http://localhost:{port}/input
    - WS ws://localhost:{port}/ws
    - GET http://localhost:{port}/health
    - GET http://localhost:{port}/info
    """
    from .agent import create_coding_agent

    def agent_factory():
        return create_coding_agent(
            model=model,
            max_iterations=max_iterations,
            auto_approve=True,  # Always auto-approve in web mode
            web_mode=True,
        )

    # Start server with open trust (no auth required)
    # relay_url=None disables P2P discovery
    host(agent_factory, port=port, trust="open", relay_url=None)
