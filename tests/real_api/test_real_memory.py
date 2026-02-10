"""Real API tests for Memory integration with Agent."""

import pytest

from connectonion import Agent, Memory
from tests.real_api.conftest import requires_openai


pytestmark = pytest.mark.real_api


@pytest.fixture
def memory_instance(tmp_path):
    """Create a Memory instance for testing."""
    memory_dir = tmp_path / "memories"
    return Memory(memory_dir=str(memory_dir))


@requires_openai
def test_agent_uses_memory_naturally(memory_instance):
    """Test that an agent can use memory in natural conversation."""
    agent = Agent(
        "memory-agent",
        system_prompt="You are a helpful assistant with memory. Save important information when asked.",
        tools=[memory_instance]
    )

    # Ask agent to remember something
    result = agent.input("Remember that Alice prefers email communication")
    assert result is not None

    # Ask agent to recall
    result = agent.input("What do you know about Alice?")
    assert result is not None
