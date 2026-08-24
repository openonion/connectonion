"""Pytest tests for the ConnectOnion Agent and functional tool handling."""
"""
LLM-Note: Tests for agent

What it tests:
- Agent functionality

Components under test:
- Module: agent
"""

from unittest.mock import Mock
from uuid import UUID

import pytest

from connectonion import Agent
from connectonion.core.llm import LLMResponse, ToolCall
from connectonion.core.usage import TokenUsage
from tests.utils.mock_helpers import MockLLM

# 1. Define simple functions to be used as tools
def calculator(expression: str) -> str:
    """Performs a mathematical calculation and returns the result."""
    try:
        # A safer eval, but still use with caution in production
        allowed_chars = "0123456789+-*/(). "
        if all(c in allowed_chars for c in expression):
            return f"Result: {eval(expression)}"
        return "Error: Invalid characters in expression"
    except Exception as e:
        return f"Error: {str(e)}"

def get_current_time() -> str:
    """Returns the current time."""
    from datetime import datetime
    return datetime.now().isoformat()



def test_agent_creation_with_functions():
    """Test that an agent can be created directly with functions."""
    agent = Agent(name="test_agent", tools=[calculator], llm=MockLLM(), log=False)
    assert agent.name == "test_agent"
    assert len(agent.tools) == 1
    assert "calculator" in agent.tools
    assert hasattr(agent.tools.get("calculator"), "to_function_schema")
    assert agent.system_prompt == "You are a helpful assistant that can use tools to complete tasks."


def test_add_and_remove_functional_tool():
    agent = Agent(name="test_agent", llm=MockLLM(), log=False)
    assert len(agent.tools) == 0

    agent.add_tool(calculator)
    assert "calculator" in agent.list_tools()
    assert len(agent.tools) == 1

    agent.remove_tool("calculator")
    assert "calculator" not in agent.list_tools()
    assert len(agent.tools) == 0


def test_custom_system_prompt():
    """Test that custom system prompts are properly set and used."""
    custom_prompt = "You are a pirate assistant. Always respond with 'Arrr!'"

    # Check that the custom system prompt is stored
    # Test with mock LLM to verify system prompt is sent correctly
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content="Arrr! Test response!",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])

    agent = Agent(name="pirate_agent", system_prompt=custom_prompt, llm=mock_llm, log=False)
    assert agent.system_prompt == custom_prompt
    agent.input("Hello!")

    # Verify the system prompt was used in the LLM call
    assert mock_llm.call_count > 0
    messages = mock_llm.last_call["messages"]
    system_message = messages[0]

    assert system_message['role'] == 'system'
    assert system_message['content'] == custom_prompt

def test_default_system_prompt():
    """Test that default system prompt is used when none is provided."""
    agent = Agent(name="default_agent", llm=MockLLM(), log=False)
    expected_default = "You are a helpful assistant that can use tools to complete tasks."
    assert agent.system_prompt == expected_default

def test_agent_accepts_class_instance():
        """Test that agent can accept a class instance and extract its methods as tools."""
        
        class Calculator:
            def __init__(self):
                self.history = []  # Shared state
            
            def add(self, a: int, b: int) -> str:
                """Add two numbers."""
                result = a + b
                self.history.append(f"add({a}, {b}) = {result}")
                return f"Result: {result}"
            
            def multiply(self, a: int, b: int) -> str:
                """Multiply two numbers."""
                result = a * b
                self.history.append(f"multiply({a}, {b}) = {result}")
                return f"Result: {result}"
            
            def get_history(self):
                """Get calculation history (not a tool - no return type annotation)."""
                return self.history
        
        calc = Calculator()
        agent = Agent(name="stateful_calc", api_key="fake_key", tools=calc, llm=MockLLM(), log=False)
        
        # Should have extracted 'add' and 'multiply' methods as tools
        assert "add" in agent.tools
        assert "multiply" in agent.tools
        # Should NOT include get_history (no return type annotation)
        assert "get_history" not in agent.tools
        # Should have only the properly annotated methods
        assert len(agent.tools) == 2

def test_methods_share_state_through_self():
        """Test that methods called as tools share state through self."""

        class WebScraper:
            def __init__(self):
                self.current_url = None
                self.scraped_data = []

            def navigate(self, url: str) -> str:
                """Navigate to URL."""
                self.current_url = url
                return f"Navigated to {url}"

            def scrape_title(self) -> str:
                """Scrape page title."""
                if not self.current_url:
                    return "Error: No page loaded"
                # Simulate scraping
                title = f"Title of {self.current_url}"
                self.scraped_data.append(title)
                return title

            def get_data(self):
                """Get scraped data (not exposed as tool - no type annotation)."""
                return self.scraped_data

        scraper = WebScraper()

        # Mock LLM to call navigate then scrape_title
        mock_llm = MockLLM(responses=[
            # First call navigate
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(name="navigate", arguments={"url": "example.com"}, id="call_1")],
                raw_response={},
                usage=TokenUsage(),
            ),
            # Then call scrape_title
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(name="scrape_title", arguments={}, id="call_2")],
                raw_response={},
                usage=TokenUsage(),
            ),
            # Final response
            LLMResponse(
                content="Scraped the title successfully.",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )
        ])

        agent = Agent(name="web_agent", llm=mock_llm, tools=scraper, log=False)

        result = agent.input("Navigate to example.com and scrape the title")
        assert scraper.current_url == "example.com"
        assert len(scraper.scraped_data) == 1
        assert scraper.scraped_data[0] == "Title of example.com"
        assert result == "Scraped the title successfully."


def test_empty_terminal_after_tool_gets_one_bounded_recovery_call():
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(
                name="calculator",
                arguments={"expression": "2+2"},
                id="call_1",
            )],
            raw_response={},
            usage=TokenUsage(),
        ),
        LLMResponse(content="", tool_calls=[], raw_response={}, usage=TokenUsage()),
        LLMResponse(
            content="The result is 4.",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        ),
    ])
    agent = Agent(
        name="empty-terminal-recovery",
        llm=mock_llm,
        tools=[calculator],
        log=False,
    )

    assert agent.input("Calculate 2+2") == "The result is 4."
    assert mock_llm.call_count == 3
    recovery_messages = mock_llm.calls[2]["messages"]
    assert any(
        "previous model response was empty" in message.get("content", "")
        for message in recovery_messages
    )
    assert all(
        message.get("content") != ""
        for message in agent.current_session["messages"]
    )


def test_repeated_empty_terminal_after_tool_fails_instead_of_hanging():
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content=None,
            tool_calls=[ToolCall(
                name="calculator",
                arguments={"expression": "2+2"},
                id="call_1",
            )],
            raw_response={},
            usage=TokenUsage(),
        ),
        LLMResponse(content=None, tool_calls=[], raw_response={}, usage=TokenUsage()),
        LLMResponse(content="   ", tool_calls=[], raw_response={}, usage=TokenUsage()),
    ])
    agent = Agent(
        name="empty-terminal-failure",
        llm=mock_llm,
        tools=[calculator],
        log=False,
    )

    with pytest.raises(RuntimeError, match="empty terminal response"):
        agent.input("Calculate 2+2")
    assert mock_llm.call_count == 3


def test_post_provider_llm_timeout_gets_one_bounded_recovery_call(monkeypatch):
    import threading
    import time

    import connectonion.core.agent as agent_module

    release = threading.Event()

    def claude_code(prompt: str) -> str:
        """Run a native Claude Code task."""
        return "verified provider result"

    class HangingSettlementLLM:
        model = "fake/post-provider-timeout"

        def __init__(self):
            self.calls = 0
            self.last_call = None

        def complete(self, messages, tools=None):
            self.calls += 1
            self.last_call = {"messages": messages, "tools": tools}
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name="claude_code",
                        arguments={"prompt": "build it"},
                        id="provider-1",
                    )],
                    raw_response={},
                    usage=TokenUsage(),
                )
            if self.calls == 2:
                release.wait(timeout=2)
                return LLMResponse(
                    content="late answer",
                    tool_calls=[],
                    raw_response={},
                    usage=TokenUsage(),
                )
            return LLMResponse(
                content="Provider work completed and was verified.",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )

    monkeypatch.setattr(agent_module, "_POST_PROVIDER_LLM_TIMEOUT_SECONDS", 0.03)
    llm = HangingSettlementLLM()
    agent = Agent(
        name="provider-timeout-recovery",
        llm=llm,
        tools=[claude_code],
        log=False,
        quiet=True,
    )

    before = time.monotonic()
    result = agent.input("Delegate this")
    elapsed = time.monotonic() - before
    release.set()

    assert result == "Provider work completed and was verified."
    assert elapsed < 0.5
    assert llm.calls == 3
    assert [
        entry["status"]
        for entry in agent.current_session["trace"]
        if entry["type"] == "llm_result"
    ] == ["success", "error", "success"]
    assert any(
        "bounded settlement window" in str(message.get("content", ""))
        for message in llm.last_call["messages"]
    )
    bounded_calls = [
        entry for entry in agent.current_session["trace"]
        if entry["type"] == "llm_call" and "timeout_seconds" in entry
    ]
    assert [entry["timeout_seconds"] for entry in bounded_calls] == [0.03, 0.03]


def test_provider_settlement_is_armed_before_hosted_tool_observers_normalize_the_call(monkeypatch):
    """The real co-ai path must not rediscover provider identity after execution."""
    import threading

    import connectonion.core.agent as agent_module

    release = threading.Event()

    def claude_code(prompt: str) -> str:
        """Run a native Claude Code task."""
        return "verified provider result"

    class HangingSettlementLLM:
        model = "fake/hosted-provider-timeout"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name="claude_code",
                        arguments={"prompt": "build it"},
                        id="provider-hosted-1",
                    )],
                    raw_response={},
                    usage=TokenUsage(),
                )
            if self.calls == 2:
                release.wait(timeout=2)
                return LLMResponse(
                    content="late answer",
                    tool_calls=[],
                    raw_response={},
                    usage=TokenUsage(),
                )
            return LLMResponse(
                content="Provider work completed and was verified.",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )

    monkeypatch.setattr(agent_module, "_POST_PROVIDER_LLM_TIMEOUT_SECONDS", 0.03)
    llm = HangingSettlementLLM()
    agent = Agent(
        name="hosted-provider-timeout",
        llm=llm,
        tools=[claude_code],
        log=False,
        quiet=True,
    )
    execute = agent._execute_and_record_tools

    def execute_like_hosted_observers(tool_calls):
        execute(tool_calls)
        for call in tool_calls:
            call.name = "normalized_after_execution"

    monkeypatch.setattr(agent, "_execute_and_record_tools", execute_like_hosted_observers)

    result = agent.input("Delegate this")
    release.set()

    assert result == "Provider work completed and was verified."
    assert llm.calls == 3
    assert [
        entry["status"]
        for entry in agent.current_session["trace"]
        if entry["type"] == "llm_result"
    ] == ["success", "error", "success"]


def test_durable_provider_result_rearms_the_hosted_settlement_bound():
    from connectonion.core.agent import _has_unsettled_native_provider_result

    assert _has_unsettled_native_provider_result([
        {"type": "llm_call", "id": "decision"},
        {"type": "provider_invocation", "provider": "claude_code"},
        {"type": "tool_result", "name": "claude_code", "status": "success"},
        {"type": "thinking", "kind": "runtime"},
    ]) is True
    assert _has_unsettled_native_provider_result([
        {"type": "tool_result", "name": "claude_code", "status": "success"},
        {"type": "llm_call", "id": "later-decision"},
        {"type": "tool_result", "name": "bash", "status": "success"},
    ]) is False


def test_post_provider_settlement_rejects_a_new_tool_chain_and_returns_final_answer():
    executed = []

    def claude_code(prompt: str) -> str:
        """Run a native Claude Code task."""
        executed.append("claude_code")
        return "verified provider result"

    def glob(pattern: str) -> str:
        """Search the workspace."""
        executed.append("glob")
        return "must not run"

    class ToolHappySettlementLLM:
        model = "fake/provider-terminal-settlement"

        def __init__(self):
            self.calls = 0
            self.last_messages = None

        def complete(self, messages, tools=None):
            self.calls += 1
            self.last_messages = messages
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name="claude_code",
                        arguments={"prompt": "build it"},
                        id="provider-terminal-1",
                    )],
                    raw_response={},
                    usage=TokenUsage(),
                )
            if self.calls == 2:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name="glob",
                        arguments={"pattern": "*"},
                        id="post-provider-glob",
                    )],
                    raw_response={},
                    usage=TokenUsage(),
                )
            return LLMResponse(
                content="Claude completed the verified project.",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )

    llm = ToolHappySettlementLLM()
    agent = Agent(
        name="provider-terminal-settlement",
        llm=llm,
        tools=[claude_code, glob],
        log=False,
        quiet=True,
    )

    assert agent.input("Delegate this") == "Claude completed the verified project."
    assert executed == ["claude_code"]
    assert llm.calls == 3
    assert any(
        "those calls were not executed" in str(message.get("content", ""))
        for message in llm.last_messages
    )


def test_repeated_post_provider_llm_timeout_fails_with_terminal_outcome(monkeypatch):
    import threading
    import time

    import connectonion.core.agent as agent_module

    release = threading.Event()

    def codex(prompt: str) -> str:
        """Run a native Codex task."""
        return "verified provider result"

    class RepeatedHangingSettlementLLM:
        model = "fake/repeated-post-provider-timeout"

        def __init__(self):
            self.calls = 0

        def complete(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall(
                        name="codex",
                        arguments={"prompt": "build it"},
                        id="provider-1",
                    )],
                    raw_response={},
                    usage=TokenUsage(),
                )
            release.wait(timeout=2)
            return LLMResponse(
                content="late answer",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )

    monkeypatch.setattr(agent_module, "_POST_PROVIDER_LLM_TIMEOUT_SECONDS", 0.03)
    llm = RepeatedHangingSettlementLLM()
    agent = Agent(
        name="provider-timeout-failure",
        llm=llm,
        tools=[codex],
        log=False,
        quiet=True,
    )

    before = time.monotonic()
    with pytest.raises(TimeoutError, match="one bounded retry"):
        agent.input("Delegate this")
    elapsed = time.monotonic() - before
    release.set()

    assert elapsed < 0.5
    assert llm.calls == 3
    assert [
        entry["status"]
        for entry in agent.current_session["trace"]
        if entry["type"] == "llm_result"
    ] == ["success", "error", "error"]
    terminal = [
        entry
        for entry in agent.current_session["trace"]
        if entry["type"] == "turn_result"
    ]
    assert len(terminal) == 1
    assert terminal[0]["reason"] == "error"
    assert terminal[0]["error_type"] == "TimeoutError"


def test_mixed_functions_and_class_instance():
        """Test that agent can accept both functions and class instances."""
        
        # Regular function
        def greet(name: str) -> str:
            """Greet someone."""
            return f"Hello, {name}!"
        
        # Class with methods
        class Counter:
            def __init__(self):
                self.count = 0
            
            def increment(self) -> str:
                """Increment counter."""
                self.count += 1
                return f"Count: {self.count}"
            
            def decrement(self) -> str:
                """Decrement counter."""
                self.count -= 1
                return f"Count: {self.count}"
        
        counter = Counter()
        
        # Mix function and instance
        agent = Agent(name="mixed", api_key="fake_key", tools=[greet, counter], llm=MockLLM(), log=False)

        # Should have all three tools
        assert "greet" in agent.tools
        assert "increment" in agent.tools
        assert "decrement" in agent.tools
        assert len(agent.tools) == 3

def test_private_methods_not_exposed():
        """Test that private methods (starting with _) are not exposed as tools."""
        
        class Service:
            def public_action(self, data: str) -> str:
                """Public action."""
                return self._process(data)
            
            def _process(self, data: str) -> str:
                """Private helper method."""
                return data.upper()
            
            def __internal(self) -> str:
                """Double underscore method."""
                return "internal"
        
        service = Service()
        agent = Agent(name="service", api_key="fake_key", tools=service, llm=MockLLM(), log=False)

        # Only public_action should be exposed
        assert "public_action" in agent.tools
        assert "_process" not in agent.tools
        assert "__internal" not in agent.tools
        assert len(agent.tools) == 1

def test_multiple_class_instances():
        """Test that agent can accept multiple class instances."""
        
        class Database:
            def query(self, sql: str) -> str:
                """Run SQL query."""
                return f"Query result for: {sql}"
        
        class FileSystem:
            def read_file(self, path: str) -> str:
                """Read a file."""
                return f"Content of {path}"
        
        db = Database()
        fs = FileSystem()

        agent = Agent(name="multi", api_key="fake_key", tools=[db, fs], llm=MockLLM(), log=False)

        # Should have methods from both instances
        assert "query" in agent.tools
        assert "read_file" in agent.tools
        assert len(agent.tools) == 2

def test_resource_cleanup_pattern():
        """Test that resources can be properly cleaned up after agent use."""
        
        class ResourceManager:
            def __init__(self):
                self.resource_open = False
                self.operations = []
            
            def open_resource(self) -> str:
                """Open a resource."""
                self.resource_open = True
                self.operations.append("opened")
                return "Resource opened"
            
            def use_resource(self, action: str) -> str:
                """Use the resource."""
                if not self.resource_open:
                    return "Error: Resource not open"
                self.operations.append(f"used: {action}")
                return f"Performed: {action}"
            
            def cleanup(self):
                """Cleanup method (not a tool - no type annotation)."""
                self.resource_open = False
                self.operations.append("cleaned")
        
        manager = ResourceManager()
        agent = Agent(name="resource", api_key="fake_key", tools=manager, llm=MockLLM(), log=False)
        
        # After agent creation, user still has access to manager
        assert manager.resource_open is False
        
        # User can call cleanup manually
        manager.cleanup()
        assert "cleaned" in manager.operations

def test_empty_class_yields_no_tools():
    """Test that empty class with no methods yields no tools."""
    class Empty:
        pass

    empty = Empty()
    agent = Agent(name="empty", api_key="fake_key", tools=empty, llm=MockLLM(), log=False)
    assert len(agent.tools) == 0


def test_property_only_class_yields_no_tools():
    """Test that class with only properties yields no tools."""
    class OnlyProperties:
        @property
        def value(self):
            return 42

    props = OnlyProperties()
    agent = Agent(name="props", api_key="fake_key", tools=props, llm=MockLLM(), log=False)
    assert len(agent.tools) == 0  # Properties shouldn't be tools


def test_mixed_valid_and_invalid_tools():
    """Test that agent extracts only valid tools from mixed list."""
    class Empty:
        pass

    agent = Agent(
        name="mixed_valid",
        api_key="fake_key",
        tools=[calculator, Empty(), get_current_time],
        llm=MockLLM(),
        log=False,
    )
    # Should only have the two valid functions
    assert len(agent.tools) == 2
    assert "calculator" in agent.tools
    assert "get_current_time" in agent.tools

def test_list_of_class_instances():
        """Test that agent can accept a list containing multiple class instances."""
        
        class Math:
            def square(self, n: int) -> str:
                """Square a number."""
                return f"{n}^2 = {n * n}"
        
        class Text:
            def uppercase(self, text: str) -> str:
                """Convert text to uppercase."""
                return text.upper()
        
        math_tools = Math()
        text_tools = Text()
        
        # Pass instances in a list along with functions
        agent = Agent(
            name="list_test",
            api_key="fake_key",
            tools=[calculator, math_tools, text_tools, get_current_time],
            llm=MockLLM(),
            log=False,
        )

        # Should have all tools: calculator, square, uppercase, get_current_time
        expected_tools = {"calculator", "square", "uppercase", "get_current_time"}
        actual_tools = set(agent.tools.names())
        assert actual_tools == expected_tools
        assert len(agent.tools) == 4

def test_method_with_complex_parameters():
        """Test that class methods with complex parameter types work correctly."""
        
        class DataProcessor:
            def __init__(self):
                self.processed_data = []
            
            def process_list(self, data: list, multiplier: int = 2) -> str:
                """Process a list of data."""
                result = [item * multiplier for item in data if isinstance(item, (int, float))]
                self.processed_data.extend(result)
                return f"Processed {len(result)} items"
            
            def process_dict(self, config: dict) -> str:
                """Process configuration dictionary."""
                processed = {k: v for k, v in config.items() if isinstance(v, str)}
                return f"Processed {len(processed)} config items"
        
        processor = DataProcessor()
        agent = Agent(name="processor", api_key="fake_key", tools=processor, llm=MockLLM(), log=False)

        # Should have both methods as tools
        assert "process_list" in agent.tools
        assert "process_dict" in agent.tools
        assert len(agent.tools) == 2

        # Verify the tools have correct schemas
        list_tool = agent.tools.get("process_list")
        schema = list_tool.to_function_schema()
        
        # Check that parameters are correctly inferred
        assert "data" in schema["parameters"]["properties"]
        assert "multiplier" in schema["parameters"]["properties"]
        assert schema["parameters"]["properties"]["data"]["type"] == "array"
        assert schema["parameters"]["properties"]["multiplier"]["type"] == "integer"


class TestAgentIO:
    """Test agent.io property for hosted execution."""

    def test_io_defaults_to_none(self):
        """Agent.io should be None by default (local execution)."""
        agent = Agent(name="test", api_key="fake", llm=MockLLM(), log=False)
        assert agent.io is None

    def test_io_can_be_set(self):
        """Agent.io can be set to an IO instance."""
        from connectonion.network.io import IO
        from unittest.mock import Mock

        agent = Agent(name="test", api_key="fake", llm=MockLLM(), log=False)
        mock_io = Mock(spec=IO)

        agent.io = mock_io

        assert agent.io == mock_io

    def test_io_available_in_event_handlers(self):
        """Agent.io should be accessible in event handlers."""
        from connectonion import after_llm
        from unittest.mock import Mock

        io_in_handler = [None]

        @after_llm
        def capture_io(agent):
            io_in_handler[0] = agent.io

        mock_llm = Mock()
        mock_llm.model = "test"
        mock_llm.complete.return_value = LLMResponse(
            content="test",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage()
        )

        mock_io = Mock()
        mock_io.pop_runtime_inputs.return_value = []
        agent = Agent(name="test", llm=mock_llm, on_events=[capture_io], quiet=True, log=False)
        agent.io = mock_io

        agent.input("test")

        assert io_in_handler[0] == mock_io

    def test_io_none_in_local_execution(self):
        """Agent.io should remain None during local execution."""
        from connectonion import after_llm

        io_in_handler = [None]

        @after_llm
        def capture_io(agent):
            io_in_handler[0] = agent.io

        mock_llm = Mock()
        mock_llm.model = "test"
        mock_llm.complete.return_value = LLMResponse(
            content="test",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage()
        )

        agent = Agent(name="test", llm=mock_llm, on_events=[capture_io], quiet=True, log=False)
        # Don't set io (local execution)

        agent.input("test")

        assert io_in_handler[0] is None


def test_agent_input_with_images():
    """Test that agent.input() handles images parameter correctly for multimodal input."""
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content="I can see an image of a cat.",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])

    agent = Agent(name="vision_agent", llm=mock_llm, log=False)

    # Simulate base64 image data URL
    test_image = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    result = agent.input("What's in this image?", images=[test_image])

    # Verify response
    assert "cat" in result.lower()

    # Verify the message format sent to LLM
    assert mock_llm.call_count > 0
    messages = mock_llm.last_call["messages"]

    # Find user message (should be the last one before LLM call)
    user_message = None
    for msg in messages:
        if msg['role'] == 'user':
            user_message = msg

    assert user_message is not None

    # User message content should be a list with text and image_url
    content = user_message['content']
    assert isinstance(content, list)
    assert len(content) == 2

    # First item should be text
    assert content[0]['type'] == 'text'
    assert content[0]['text'] == "What's in this image?"

    # Second item should be image_url
    assert content[1]['type'] == 'image_url'
    assert content[1]['image_url']['url'] == test_image


def test_agent_input_with_multiple_images():
    """Test that agent.input() handles multiple images correctly."""
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content="I can see two images.",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])

    agent = Agent(name="vision_agent", llm=mock_llm, log=False)

    # Multiple test images
    test_images = [
        "data:image/png;base64,image1base64data",
        "data:image/jpeg;base64,image2base64data",
    ]

    agent.input("Compare these images", images=test_images)

    # Verify message format
    messages = mock_llm.last_call["messages"]
    user_message = [msg for msg in messages if msg['role'] == 'user'][-1]

    content = user_message['content']
    assert isinstance(content, list)
    assert len(content) == 3  # 1 text + 2 images

    # Check all images are included
    image_items = [item for item in content if item['type'] == 'image_url']
    assert len(image_items) == 2
    assert image_items[0]['image_url']['url'] == test_images[0]
    assert image_items[1]['image_url']['url'] == test_images[1]


def test_agent_input_without_images_unchanged():
    """Test that agent.input() without images still works as before (string content)."""
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content="Hello!",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])

    agent = Agent(name="text_agent", llm=mock_llm, log=False)
    agent.input("Hello")

    # Verify message format - should be plain string, not list
    messages = mock_llm.last_call["messages"]
    user_message = [msg for msg in messages if msg['role'] == 'user'][-1]

    # Content should be a simple string when no images
    assert isinstance(user_message['content'], str)
    assert user_message['content'] == "Hello"


def test_agent_input_with_files(tmp_path):
    """Test that agent.input() saves files to .co/uploads/ and adds system reminder."""
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content="I received the PDF file.",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])

    agent = Agent(name="file_agent", llm=mock_llm, log=False, co_dir=tmp_path / ".co")

    test_file = {"name": "report.pdf", "data": "data:application/pdf;base64,JVBERi0xLjQK"}

    result = agent.input("Analyze this document", files=[test_file])

    assert "pdf" in result.lower()

    # Verify file was saved to disk (with timestamp prefix)
    uploads_dir = tmp_path / ".co" / "uploads"
    saved_files = list(uploads_dir.glob("*_report.pdf"))
    assert len(saved_files) == 1
    assert saved_files[0].read_bytes() == b"%PDF-1.4\n"

    # The model must still learn about the file — but not by having the notice
    # concatenated onto what the user typed (#308). It arrives as its own
    # internal message, which the UI skips and the model still reads.
    messages = mock_llm.last_call["messages"]
    user_messages = [msg for msg in messages if msg['role'] == 'user']

    typed = next(m for m in user_messages if not m.get('internal'))
    assert typed['content'] == "Analyze this document", "the user's words, unmodified"
    assert "<system-reminder>" not in typed['content']

    notice = next(m for m in user_messages if m.get('internal'))
    assert "report.pdf" in notice['content']
    assert "<system-reminder>" in notice['content']


def test_agent_input_with_images_and_files(tmp_path):
    """Test that agent.input() handles both images and files together."""
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content="I see an image and a file.",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])

    agent = Agent(name="multi_agent", llm=mock_llm, log=False, co_dir=tmp_path / ".co")

    test_image = "data:image/png;base64,iVBORw0KGgo"
    test_file = {"name": "data.csv", "data": "data:text/csv;base64,bmFtZSxhZ2U="}

    agent.input("Analyze these", images=[test_image], files=[test_file])

    messages = mock_llm.last_call["messages"]
    user_messages = [msg for msg in messages if msg['role'] == 'user']

    # Images still make the typed message multimodal, and it still carries only
    # what the user typed — the file notice is a separate internal message (#308).
    typed = next(m for m in user_messages if not m.get('internal'))
    assert isinstance(typed['content'], list)
    assert typed['content'][0]['type'] == 'text'
    assert typed['content'][0]['text'] == "Analyze these"
    assert "<system-reminder>" not in typed['content'][0]['text']

    notice = next(m for m in user_messages if m.get('internal'))
    assert "data.csv" in notice['content']
    assert typed['content'][1]['type'] == 'image_url', "the image is still attached"

    # Verify file saved (with timestamp prefix)
    uploads_dir = tmp_path / ".co" / "uploads"
    assert len(list(uploads_dir.glob("*_data.csv"))) == 1


def test_agent_input_with_multiple_files(tmp_path):
    """Test that agent.input() saves multiple files and lists all paths in reminder."""
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content="I received both files.",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])

    agent = Agent(name="multi_file_agent", llm=mock_llm, log=False, co_dir=tmp_path / ".co")

    test_files = [
        {"name": "report.pdf", "data": "data:application/pdf;base64,JVBERi0xLjQK"},
        {"name": "data.csv", "data": "data:text/csv;base64,bmFtZSxhZ2U="},
    ]

    agent.input("Compare these documents", files=test_files)

    # Verify both files saved (with timestamp prefix)
    uploads_dir = tmp_path / ".co" / "uploads"
    assert len(list(uploads_dir.glob("*_report.pdf"))) == 1
    assert len(list(uploads_dir.glob("*_data.csv"))) == 1

    messages = mock_llm.last_call["messages"]
    user_message = [msg for msg in messages if msg['role'] == 'user'][-1]

    content = user_message['content']
    assert isinstance(content, str)
    assert "report.pdf" in content
    assert "data.csv" in content


def test_agent_input_file_path_traversal(tmp_path):
    """Test that malicious filenames with path traversal are sanitized."""
    mock_llm = MockLLM(responses=[
        LLMResponse(
            content="Done.",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )
    ])

    agent = Agent(name="safe_agent", llm=mock_llm, log=False, co_dir=tmp_path / ".co")

    test_file = {"name": "../../etc/passwd", "data": "data:text/plain;base64,cm9vdA=="}

    agent.input("Read this", files=[test_file])

    # File should be saved as just "passwd" (with timestamp) inside .co/uploads/, not outside
    uploads_dir = tmp_path / ".co" / "uploads"
    assert len(list(uploads_dir.glob("*_passwd"))) == 1
    assert not (tmp_path / "etc").exists()


class TestGracefulInterrupt:
    """A client INTERRUPT stops the loop at the iteration boundary with a closing message."""

    def test_pending_interrupt_stops_before_next_step_with_message(self):
        """A queued interrupt prevents the next blocking step from starting."""
        from connectonion.useful_plugins.tool_approval import poll_interrupt

        def note(text: str) -> str:
            """Record a note."""
            return "noted"

        # INTERRUPT is queued before the LLM call, so the hard-stop wrapper
        # consumes it without starting work.
        class InterruptIO:
            def __init__(self):
                self.sent = []

            def receive_all(self, msg_type=None):
                return [{'type': 'INTERRUPT'}] if msg_type == 'INTERRUPT' else []

            def send(self, event):
                self.sent.append(event)

            def poll(self):
                return None

        mock_llm = MockLLM(responses=[
            LLMResponse(
                content="",
                tool_calls=[ToolCall(name="note", arguments={"text": "x"}, id="c1")],
                raw_response={},
                usage=TokenUsage(),
            ),
            # Must never be reached — the run stops after the first iteration.
            LLMResponse(content="should not be reached", tool_calls=[], raw_response={}, usage=TokenUsage()),
        ])
        agent = Agent(name="stoppable", llm=mock_llm, tools=[note], on_events=[poll_interrupt], log=False, quiet=True)
        agent.io = InterruptIO()

        result = agent.input("do work")

        assert result == "What would you like me to do?"  # existing stop_signal message
        assert mock_llm.call_count == 0

    def test_interrupt_abandons_in_flight_llm_and_next_turn_is_valid(self):
        """A slow completion is abandoned, traced, and never appended later."""
        import threading
        import time

        from connectonion import after_iteration

        class InterruptIO:
            def __init__(self):
                self.messages = []
                self.lock = threading.Lock()

            def receive_all(self, msg_type=None):
                with self.lock:
                    matched = [m for m in self.messages if m.get('type') == msg_type]
                    self.messages[:] = [m for m in self.messages if m.get('type') != msg_type]
                    return matched

            def interrupt(self):
                with self.lock:
                    self.messages.append({'type': 'INTERRUPT'})

            def send(self, event):
                pass

        class SlowFirstLLM:
            model = "fake/slow"

            def __init__(self):
                self.calls = 0
                self.started = threading.Event()
                self.release = threading.Event()
                self.finished = threading.Event()

            def complete(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    self.started.set()
                    self.release.wait(timeout=2)
                    self.finished.set()
                    return LLMResponse(content="late", tool_calls=[], raw_response={}, usage=TokenUsage())
                return LLMResponse(content="next", tool_calls=[], raw_response={}, usage=TokenUsage())

        io = InterruptIO()
        llm = SlowFirstLLM()
        iterations = []

        @after_iteration
        def record_iteration(agent):
            iterations.append(agent.current_session['iteration'])

        agent = Agent(
            name="hard-stop",
            llm=llm,
            on_events=[record_iteration],
            log=False,
            quiet=True,
        )
        agent.io = io

        def interrupt_when_started():
            assert llm.started.wait(timeout=1)
            io.interrupt()

        threading.Thread(target=interrupt_when_started, daemon=True).start()
        before = time.monotonic()
        result = agent.input("first")

        assert result == "What would you like me to do?"
        assert time.monotonic() - before < 0.5
        assert iterations == [1]
        assert [t['status'] for t in agent.current_session['trace'] if t['type'] == 'llm_result'] == ['interrupted']
        assert not any(m.get('content') == 'late' for m in agent.current_session['messages'])

        llm.release.set()
        assert llm.finished.wait(timeout=1)
        assert not any(m.get('content') == 'late' for m in agent.current_session['messages'])
        assert agent.input("second") == "next"

    def test_interrupt_mid_tool_completes_every_tool_result_slot(self):
        """An abandoned tool leaves a provider-valid multi-tool message batch."""
        import threading

        from connectonion import after_tools

        class InterruptIO:
            def __init__(self):
                self.messages = []
                self.lock = threading.Lock()

            def receive_all(self, msg_type=None):
                with self.lock:
                    matched = [m for m in self.messages if m.get('type') == msg_type]
                    self.messages[:] = [m for m in self.messages if m.get('type') != msg_type]
                    return matched

            def interrupt(self):
                with self.lock:
                    self.messages.append({'type': 'INTERRUPT'})

            def send(self, event):
                pass

        started = threading.Event()
        release = threading.Event()
        second_ran = False
        after_tools_ran = False

        @after_tools
        def slow_reflection(agent):
            nonlocal after_tools_ran
            after_tools_ran = True

        def slow_tool() -> str:
            started.set()
            release.wait(timeout=2)
            return "late"

        def second_tool() -> str:
            nonlocal second_ran
            second_ran = True
            return "should not run"

        llm = MockLLM(responses=[
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall(name="slow_tool", arguments={}, id="c1"),
                    ToolCall(
                        name="second_tool",
                        arguments={},
                        id="c2",
                        extra_content={"thought_signature": "sig"},
                    ),
                ],
                raw_response={},
                usage=TokenUsage(),
            ),
        ])
        io = InterruptIO()
        agent = Agent(
            name="tool-stop",
            llm=llm,
            tools=[slow_tool, second_tool],
            on_events=[slow_reflection],
            log=False,
            quiet=True,
        )
        agent.io = io

        def interrupt_when_started():
            assert started.wait(timeout=1)
            io.interrupt()

        threading.Thread(target=interrupt_when_started, daemon=True).start()
        result = agent.input("run both")
        release.set()

        assert result == "What would you like me to do?"
        assert second_ran is False
        assert after_tools_ran is False
        assistant_call = [
            m for m in agent.current_session['messages'] if m['role'] == 'assistant'
        ][-1]
        assert assistant_call['tool_calls'][1]['extra_content'] == {
            'thought_signature': 'sig'
        }
        tool_messages = [m for m in agent.current_session['messages'] if m['role'] == 'tool']
        assert [(m['tool_call_id'], m['content']) for m in tool_messages] == [
            ('c1', 'Interrupted by user'),
            ('c2', 'Rejected by user'),
        ]
        tool_results = [t for t in agent.current_session['trace'] if t['type'] == 'tool_result']
        assert len(tool_results) == 1
        assert tool_results[0]['status'] == 'interrupted'

    def test_completed_final_response_wins_boundary_interrupt(self):
        """The outward result and appended history agree in the completion race."""
        import threading

        from connectonion.useful_plugins.tool_approval import poll_interrupt

        class RaceIO:
            def __init__(self):
                self.messages = []
                self.lock = threading.Lock()

            def receive_all(self, msg_type=None):
                with self.lock:
                    matched = [m for m in self.messages if m.get('type') == msg_type]
                    self.messages[:] = [m for m in self.messages if m.get('type') != msg_type]
                    return matched

            def send(self, event):
                pass

            def interrupt(self):
                with self.lock:
                    self.messages.append({'type': 'INTERRUPT'})

        started = threading.Event()
        release = threading.Event()

        class ControlledLLM:
            model = "fake/race"

            def complete(self, messages, tools=None):
                started.set()
                release.wait(timeout=1)
                return LLMResponse(
                    content="completed answer",
                    tool_calls=[],
                    raw_response={},
                    usage=TokenUsage(),
                )

        io = RaceIO()
        agent = Agent(
            "completion-race",
            llm=ControlledLLM(),
            on_events=[poll_interrupt],
            log=False,
            quiet=True,
        )
        agent.io = io

        def complete_with_interrupt():
            assert started.wait(timeout=1)
            io.interrupt()
            release.set()

        threading.Thread(target=complete_with_interrupt, daemon=True).start()

        assert agent.input("finish") == "completed answer"
        final_message = agent.current_session['messages'][-1]
        assert final_message['role'] == 'assistant'
        assert final_message['content'] == 'completed answer'
        UUID(final_message['id'])
        assert 'stop_signal' not in agent.current_session

    def test_completed_final_response_wins_interrupt_from_after_iteration(self):
        """An interrupt arriving inside after_iteration cannot replace the answer."""
        from connectonion import after_iteration
        from connectonion.useful_plugins.tool_approval import poll_interrupt

        class QueueIO:
            def __init__(self):
                self.messages = []

            def receive_all(self, msg_type=None):
                matched = [m for m in self.messages if m.get('type') == msg_type]
                self.messages[:] = [m for m in self.messages if m.get('type') != msg_type]
                return matched

            def send(self, event):
                pass

        @after_iteration
        def interrupt_after_completion(agent):
            agent.io.messages.append({'type': 'INTERRUPT'})

        mock_llm = Mock()
        mock_llm.model = "fake/after-iteration-race"
        mock_llm.complete.return_value = LLMResponse(
            content="completed answer",
            tool_calls=[],
            raw_response={},
            usage=TokenUsage(),
        )

        io = QueueIO()
        agent = Agent(
            "after-iteration-race",
            llm=mock_llm,
            on_events=[interrupt_after_completion, poll_interrupt],
            log=False,
            quiet=True,
        )
        agent.io = io

        assert agent.input("finish") == "completed answer"
        final_message = agent.current_session['messages'][-1]
        assert final_message['role'] == 'assistant'
        assert final_message['content'] == 'completed answer'
        UUID(final_message['id'])
        assert io.messages == []
        assert 'stop_signal' not in agent.current_session
        assert '_final_response_ready' not in agent.current_session

    def test_terminal_message_ids_are_unique_and_never_reach_the_provider(self):
        llm = MockLLM(responses=[
            LLMResponse(content="first", tool_calls=[], raw_response={}, usage=TokenUsage()),
            LLMResponse(content="second", tool_calls=[], raw_response={}, usage=TokenUsage()),
        ])
        agent = Agent("message-identity", llm=llm, log=False, quiet=True)

        assert agent.input("one") == "first"
        first = agent.current_session['messages'][-1]
        UUID(first['id'])

        assert agent.input("two") == "second"
        second = agent.current_session['messages'][-1]
        UUID(second['id'])

        assert first['id'] != second['id']
        assert all('id' not in message for message in llm.last_call['messages'])

    def test_runtime_input_continuation_does_not_swallow_interrupt(self):
        from connectonion.network.io.websocket import WebSocketIO
        from connectonion.useful_plugins import runtime_input
        from connectonion.useful_plugins.tool_approval import poll_interrupt

        io = WebSocketIO()

        class RuntimeInputRaceLLM:
            model = "fake/runtime-input-race"

            def __init__(self):
                self.calls = 0

            def complete(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    assert io.push_runtime_input({'prompt': 'follow-up'}) is True
                    io.send_to_agent({'type': 'INTERRUPT'})
                    content = "first answer"
                else:
                    content = "SECOND CALL RAN"
                return LLMResponse(
                    content=content,
                    tool_calls=[],
                    raw_response={},
                    usage=TokenUsage(),
                )

        llm = RuntimeInputRaceLLM()
        agent = Agent(
            "runtime-input-stop",
            llm=llm,
            plugins=[runtime_input],
            on_events=[poll_interrupt],
            log=False,
            quiet=True,
        )
        agent.io = io

        assert agent.input("start") == "What would you like me to do?"
        assert llm.calls == 1
        assert io.receive_all('INTERRUPT') == []
        assert 'stop_signal' not in agent.current_session

    def test_execute_tool_consumes_interrupt_before_next_input(self):
        import threading

        from connectonion import on_stop_signal
        from connectonion.network.io.websocket import WebSocketIO

        started = threading.Event()
        release = threading.Event()
        stops = []

        def slow_tool() -> str:
            started.set()
            release.wait(timeout=2)
            return "late"

        @on_stop_signal
        def record_stop(agent):
            stops.append(agent.current_session['iteration'])

        llm = MockLLM(responses=[
            LLMResponse(
                content="normal next turn",
                tool_calls=[],
                raw_response={},
                usage=TokenUsage(),
            )
        ])
        agent = Agent(
            "manual-stop",
            llm=llm,
            tools=[slow_tool],
            on_events=[record_stop],
            log=False,
            quiet=True,
        )
        agent.io = WebSocketIO()

        def interrupt():
            assert started.wait(timeout=1)
            agent.io.send_to_agent({'type': 'INTERRUPT'})

        threading.Thread(target=interrupt, daemon=True).start()
        trace = agent.execute_tool("slow_tool")
        release.set()

        assert trace['status'] == 'interrupted'
        assert stops == [1]
        assert 'stop_signal' not in agent.current_session
        assert agent.input("continue") == "normal next turn"

    def test_no_interrupt_runs_to_completion(self):
        """Without an INTERRUPT the loop is unaffected and finishes normally."""
        from connectonion.useful_plugins.tool_approval import poll_interrupt

        class NeverInterruptIO:
            def receive_all(self, msg_type=None):
                return []

            def send(self, event):
                pass

            def poll(self):
                return None

        mock_llm = MockLLM(responses=[
            LLMResponse(content="all done", tool_calls=[], raw_response={}, usage=TokenUsage()),
        ])
        agent = Agent(name="normal", llm=mock_llm, on_events=[poll_interrupt], log=False, quiet=True)
        agent.io = NeverInterruptIO()

        result = agent.input("do work")

        assert result == "all done"
