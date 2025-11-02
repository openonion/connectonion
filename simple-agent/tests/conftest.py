"""
Pytest configuration for ConnectOnion tests.

Defines fixtures and configuration for all tests.
"""

import pytest
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
from connectonion import Agent

# Load .env file for API keys
load_dotenv()


@pytest.fixture
def relay_url():
    """
    Default relay URL for network tests.

    Uses production relay server by default.
    Override with --relay-url flag or RELAY_URL env var.
    """
    import os
    return os.getenv("RELAY_URL", "wss://oo.openonion.ai/ws/announce")


@pytest.fixture
def local_relay_url():
    """Local relay URL for development/testing."""
    return "ws://localhost:8000/ws/announce"


@pytest.fixture
def test_agent():
    """Create a test agent with a simple search tool."""
    def search(query: str) -> str:
        """Search the web for information."""
        return f"Here are results for: {query}"

    agent = Agent(
        name="TestAgent",
        tools=[search],
        system_prompt="You are a helpful test assistant."
    )
    return agent


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--relay-url",
        action="store",
        default="wss://oo.openonion.ai/ws/announce",
        help="Relay server URL for network tests"
    )
    parser.addoption(
        "--use-local-relay",
        action="store_true",
        help="Use local relay server (ws://localhost:8000/ws/announce)"
    )


@pytest.fixture
def relay_url_from_cli(request):
    """Get relay URL from command line or use default."""
    if request.config.getoption("--use-local-relay"):
        return "ws://localhost:8000/ws/announce"
    return request.config.getoption("--relay-url")
