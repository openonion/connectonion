"""Test the plugin system implementation."""
from connectonion import Agent, after_llm, after_tool

# Simple plugin - just a list
def log_llm(agent):
    pass  # Just a marker

simple_logger = [after_llm(log_llm)]


# Plugin factory for configuration
def make_counter():
    """Create a counter plugin with state."""
    counts = {'llm': 0, 'tool': 0}

    def count_llm(agent):
        counts['llm'] += 1

    def count_tool(agent):
        counts['tool'] += 1

    return [
        after_llm(count_llm),
        after_tool(count_tool)
    ]


def test_simple_plugin():
    """Test that simple list plugins register correctly."""
    agent = Agent(
        "test_simple",
        plugins=[simple_logger],  # Pass the list directly
        log=False
    )

    # Should have 1 after_llm event handler
    assert len(agent.events['after_llm']) == 1
    # Total events should be 1
    total_events = sum(len(handlers) for handlers in agent.events.values())
    assert total_events == 1


def test_factory_plugin():
    """Test that plugin factories work for configuration."""
    counter = make_counter()  # Create the list
    agent = Agent(
        "test_factory",
        plugins=[counter],  # Pass the list
        log=False
    )

    # Should have 1 after_llm and 1 after_tool handler
    assert len(agent.events['after_llm']) == 1
    assert len(agent.events['after_tool']) == 1
    # Total events should be 2
    total_events = sum(len(handlers) for handlers in agent.events.values())
    assert total_events == 2


def test_multiple_plugins():
    """Test that multiple plugins can be registered together."""
    counter = make_counter()
    agent = Agent(
        "test_multiple",
        plugins=[simple_logger, counter],  # Two lists
        log=False
    )

    # Should have 2 after_llm handlers (one from each plugin)
    assert len(agent.events['after_llm']) == 2
    # Should have 1 after_tool handler (from counter)
    assert len(agent.events['after_tool']) == 1
    # Total events should be 3
    total_events = sum(len(handlers) for handlers in agent.events.values())
    assert total_events == 3


def test_plugins_with_on_events():
    """Test that plugins and on_events can be used together."""
    def custom_event(agent):
        pass

    agent = Agent(
        "test_combined",
        plugins=[simple_logger],
        on_events=[after_tool(custom_event)],
        log=False
    )

    # Should have 1 after_llm from plugin
    assert len(agent.events['after_llm']) == 1
    # Should have 1 after_tool from on_events
    assert len(agent.events['after_tool']) == 1
    # Total events should be 2
    total_events = sum(len(handlers) for handlers in agent.events.values())
    assert total_events == 2


def test_reusable_plugin():
    """Test that plugins can be reused across multiple agents."""
    # Create plugin once
    counter = make_counter()

    # Use it in multiple agents
    agent1 = Agent("test1", plugins=[counter], log=False)
    agent2 = Agent("test2", plugins=[counter], log=False)

    # Both should have the same events
    assert len(agent1.events['after_llm']) == 1
    assert len(agent2.events['after_llm']) == 1
