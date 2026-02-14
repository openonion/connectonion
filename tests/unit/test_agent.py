"""Pytest tests for the ConnectOnion Agent and functional tool handling."""
from unittest.mock import Mock

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
