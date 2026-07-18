"""Pytest tests for the ConnectOnion Agent and functional tool handling."""
"""
LLM-Note: Tests for agent

What it tests:
- Agent functionality

Components under test:
- Module: agent
"""

import threading
import time
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

    # Verify system reminder was appended to prompt with file path
    messages = mock_llm.last_call["messages"]
    user_message = [msg for msg in messages if msg['role'] == 'user'][-1]

    content = user_message['content']
    assert isinstance(content, str)
    assert "Analyze this document" in content
    assert "<system-reminder>" in content
    assert "report.pdf" in content


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
    user_message = [msg for msg in messages if msg['role'] == 'user'][-1]

    content = user_message['content']
    assert isinstance(content, list)
    # Images make it multimodal; file reminder is appended to prompt text
    assert content[0]['type'] == 'text'
    assert "data.csv" in content[0]['text']
    assert "<system-reminder>" in content[0]['text']
    assert content[1]['type'] == 'image_url'

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
    """A client INTERRUPT stops blocking work with a closing message."""

    def test_pending_interrupt_prevents_step_from_starting(self):
        """An already queued stop prevents the next LLM call from starting."""
        from connectonion.useful_plugins.tool_approval import poll_interrupt

        def note(text: str) -> str:
            """Record a note."""
            return "noted"

        class InterruptIO:
            def __init__(self):
                self.sent = []

            def receive_all(self, msg_type=None):
                return [{'type': 'INTERRUPT'}] if msg_type == 'INTERRUPT' else []

            def send_to_agent(self, message):
                pass

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

    def test_interrupt_abandons_llm_and_next_turn_is_valid(self):
        from connectonion import on_stop_signal
        from connectonion.network.io import WebSocketIO

        started = threading.Event()
        release = threading.Event()
        stop_events = []

        class BlockingThenImmediateLLM:
            model = "blocking-test"

            def __init__(self):
                self.calls = 0

            def complete(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    started.set()
                    release.wait(timeout=2)
                    return LLMResponse(content="late", tool_calls=[], raw_response={}, usage=TokenUsage())
                return LLMResponse(content="second turn", tool_calls=[], raw_response={}, usage=TokenUsage())

        @on_stop_signal
        def record_stop(agent):
            stop_events.append(agent.current_session['iteration'])

        io = WebSocketIO()
        llm = BlockingThenImmediateLLM()
        agent = Agent("hard-stop", llm=llm, on_events=[record_stop], log=False, quiet=True)
        agent.io = io

        sender = threading.Thread(
            target=lambda: (started.wait(timeout=1), io.send_to_agent({"type": "INTERRUPT"})),
            daemon=True,
        )
        sender.start()
        began = time.monotonic()
        first = agent.input("first turn")

        assert first == "What would you like me to do?"
        assert time.monotonic() - began < 0.8
        assert stop_events == [1]
        assert [m['role'] for m in agent.current_session['messages']] == ['system', 'user']
        llm_results = [t for t in agent.current_session['trace'] if t['type'] == 'llm_result']
        assert llm_results[-1]['status'] == 'interrupted'

        second = agent.input("second turn")
        assert second == "second turn"
        assert [m['role'] for m in agent.current_session['messages']] == [
            'system', 'user', 'user', 'assistant'
        ]

        release.set()
        time.sleep(0.02)
        assert all(message.get('content') != 'late' for message in agent.current_session['messages'])

    def test_none_llm_response_is_not_mistaken_for_user_interrupt(self):
        from connectonion import on_stop_signal

        stop_events = []

        class BrokenLLM:
            model = "broken-test"

            def complete(self, messages, tools=None):
                return None

        @on_stop_signal
        def record_stop(agent):
            stop_events.append(True)

        agent = Agent(
            "broken-llm",
            llm=BrokenLLM(),
            on_events=[record_stop],
            log=False,
            quiet=True,
        )

        with pytest.raises(AttributeError):
            agent.input("fail normally")

        assert stop_events == []

    def test_interrupt_abandons_tool_and_next_turn_has_provider_valid_history(self):
        from connectonion.core.llm import AnthropicLLM
        from connectonion.network.io import WebSocketIO

        started = threading.Event()
        release = threading.Event()
        later_called = False
        second_call_messages = []

        def slow_tool() -> str:
            started.set()
            release.wait(timeout=2)
            return "late result"

        def later_tool() -> str:
            nonlocal later_called
            later_called = True
            return "must not run"

        class ToolThenAnswerLLM:
            model = "tool-interrupt-test"

            def __init__(self):
                self.calls = 0

            def complete(self, messages, tools=None):
                self.calls += 1
                if self.calls == 1:
                    return LLMResponse(
                        content="",
                        tool_calls=[
                            ToolCall(
                                name="slow_tool",
                                arguments={},
                                id="slow-call",
                                extra_content={"google": {"thought_signature": "sig"}},
                            ),
                            ToolCall(name="later_tool", arguments={}, id="later-call"),
                        ],
                        raw_response={},
                        usage=TokenUsage(),
                    )
                second_call_messages.extend(messages)
                return LLMResponse(
                    content="next turn is valid",
                    tool_calls=[],
                    raw_response={},
                    usage=TokenUsage(),
                )

        io = WebSocketIO()
        llm = ToolThenAnswerLLM()
        agent = Agent(
            "tool-hard-stop",
            llm=llm,
            tools=[slow_tool, later_tool],
            log=False,
            quiet=True,
        )
        agent.io = io
        sender = threading.Thread(
            target=lambda: (started.wait(timeout=1), io.send_to_agent({"type": "INTERRUPT"})),
            daemon=True,
        )
        sender.start()

        assert agent.input("first turn") == "What would you like me to do?"
        assert later_called is False
        assert agent.input("second turn") == "next turn is valid"

        assistant = next(message for message in second_call_messages if message["role"] == "assistant")
        assert assistant["tool_calls"][0]["extra_content"] == {
            "google": {"thought_signature": "sig"}
        }
        tool_results = [message for message in second_call_messages if message["role"] == "tool"]
        assert [(message["tool_call_id"], message["content"]) for message in tool_results] == [
            ("slow-call", "Interrupted by user"),
            ("later-call", "Rejected by user"),
        ]

        anthropic_messages = AnthropicLLM.__new__(AnthropicLLM)._convert_messages(second_call_messages)
        tool_use_ids = [
            item["id"]
            for message in anthropic_messages
            for item in message["content"] if isinstance(message["content"], list)
            if item["type"] == "tool_use"
        ]
        tool_result_ids = [
            item["tool_use_id"]
            for message in anthropic_messages
            for item in message["content"] if isinstance(message["content"], list)
            if item["type"] == "tool_result"
        ]
        assert tool_result_ids == tool_use_ids == ["slow-call", "later-call"]

        release.set()

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
