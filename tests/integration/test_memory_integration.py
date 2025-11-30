"""Integration tests for Memory with Agent."""

import os
import shutil
import pytest
from connectonion import Agent, Memory
from unittest.mock import Mock, MagicMock


@pytest.fixture
def memory_instance():
    """Create a Memory instance for testing."""
    test_dir = "test_integration_memories"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    memory = Memory(memory_dir=test_dir)
    yield memory

    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


def test_memory_as_agent_tool(memory_instance):
    """Test that Memory can be used as an agent tool."""
    agent = Agent("test-agent", tools=[memory_instance])

    # Check that all memory methods are registered as tools
    tool_names = [tool.name for tool in agent.tools]

    assert "write_memory" in tool_names
    assert "read_memory" in tool_names
    assert "list_memories" in tool_names
    assert "search_memory" in tool_names


def test_memory_tool_schemas(memory_instance):
    """Test that Memory methods have correct tool schemas."""
    agent = Agent("test-agent", tools=[memory_instance])

    # Check write_memory schema
    write_tool = agent.tools.get("write_memory")
    assert write_tool.name == "write_memory"
    write_schema = str(write_tool.to_function_schema())
    assert "key" in write_schema
    assert "content" in write_schema

    # Check read_memory schema
    read_tool = agent.tools.get("read_memory")
    assert read_tool.name == "read_memory"
    read_schema = str(read_tool.to_function_schema())
    assert "key" in read_schema


def test_memory_methods_callable_from_agent(memory_instance):
    """Test that memory methods work when called via agent's tools."""
    agent = Agent("test-agent", tools=[memory_instance])

    # Write via tools
    write_result = agent.tools.write_memory.run("test-key", "test content")
    assert "saved" in write_result.lower()

    # Read via tools
    read_result = agent.tools.read_memory.run("test-key")
    assert "test content" in read_result


def test_multiple_agents_same_memory():
    """Test that multiple agents can share the same Memory instance."""
    shared_dir = "shared_test_memories"
    if os.path.exists(shared_dir):
        shutil.rmtree(shared_dir)

    memory = Memory(memory_dir=shared_dir)

    agent1 = Agent("agent1", tools=[memory])
    agent2 = Agent("agent2", tools=[memory])

    # Agent1 writes
    agent1.tools.write_memory.run("shared-key", "Shared content")

    # Agent2 reads
    result = agent2.tools.read_memory.run("shared-key")
    assert "Shared content" in result

    # Cleanup
    shutil.rmtree(shared_dir)


def test_memory_with_other_tools(memory_instance):
    """Test Memory works alongside other tools."""
    def calculate(expression: str) -> str:
        """Calculate a math expression."""
        return str(eval(expression))

    agent = Agent("multi-tool-agent", tools=[memory_instance, calculate])

    tool_names = [tool.name for tool in agent.tools]
    assert "write_memory" in tool_names
    assert "read_memory" in tool_names
    assert "calculate" in tool_names


@pytest.mark.real_api
def test_agent_uses_memory_naturally(memory_instance):
    """Test that an agent can use memory in natural conversation (requires API key).

    Run with: pytest tests/integration/ -m real_api
    """
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
