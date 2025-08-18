"""Tests for the ConnectOnion Agent and its functional tool handling."""

import unittest
import os
import shutil
import tempfile
from unittest.mock import Mock, patch
from connectonion import Agent
from connectonion.llm import LLMResponse, ToolCall

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


class TestAgentWithFunctionalTools(unittest.TestCase):
    """Test Agent functionality with simple function-based tools."""

    def setUp(self):
        """Set up a temporary directory for history."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up the temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_agent_creation_with_functions(self):
        """Test that an agent can be created directly with functions."""
        agent = Agent(name="test_agent", api_key="fake_key", tools=[calculator])
        self.assertEqual(agent.name, "test_agent")
        self.assertEqual(len(agent.tools), 1)
        self.assertIn("calculator", agent.tool_map)
        # Check that the function has been processed into a tool
        self.assertTrue(hasattr(agent.tool_map["calculator"], "to_function_schema"))
        # Check default system prompt
        self.assertEqual(agent.system_prompt, "You are a helpful assistant that can use tools to complete tasks.")

    def test_add_and_remove_functional_tool(self):
        """Test adding and removing tools that are simple functions."""
        agent = Agent(name="test_agent", api_key="fake_key")
        self.assertEqual(len(agent.tools), 0)

        # Add a functional tool
        agent.add_tool(calculator)
        self.assertIn("calculator", agent.list_tools())
        self.assertEqual(len(agent.tools), 1)

        # Remove the tool
        agent.remove_tool("calculator")
        self.assertNotIn("calculator", agent.list_tools())
        self.assertEqual(len(agent.tools), 0)

    @patch('connectonion.agent.OpenAILLM')
    def test_agent_run_no_tools_needed(self, mock_llm_class):
        """Test a simple run where the LLM does not need to call a tool."""
        # Mock the LLM's response
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="Hello there! I am a test assistant.",
            tool_calls=[],
            raw_response={}
        )
        mock_llm_class.return_value = mock_llm

        agent = Agent(name="test_no_tools", api_key="fake_key")
        # Override history path to use temp dir
        agent.history.history_file = os.path.join(self.temp_dir, "history.json")

        result = agent.input("Say hello")

        self.assertEqual(result, "Hello there! I am a test assistant.")
        # Verify history was recorded
        self.assertEqual(len(agent.history.records), 1)
        self.assertEqual(agent.history.records[0].user_prompt, "Say hello")
        self.assertEqual(len(agent.history.records[0].tool_calls), 0)

    @patch('connectonion.agent.OpenAILLM')
    def test_agent_run_with_single_tool_call(self, mock_llm_class):
        """Test a run where the LLM calls a single functional tool."""
        mock_llm = Mock()
        
        # Define the sequence of responses from the LLM
        mock_llm.complete.side_effect = [
            # 1. First call from user: LLM decides to use the calculator
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(name="calculator", arguments={"expression": "40 + 2"}, id="call_1")],
                raw_response={}
            ),
            # 2. After tool execution: LLM provides the final answer
            LLMResponse(
                content="The answer is 42.",
                tool_calls=[],
                raw_response={}
            )
        ]
        mock_llm_class.return_value = mock_llm

        agent = Agent(name="test_single_tool", api_key="fake_key", tools=[calculator])
        agent.history.history_file = os.path.join(self.temp_dir, "history.json")

        result = agent.input("What is 40 + 2?")

        self.assertEqual(result, "The answer is 42.")
        self.assertEqual(len(agent.history.records), 1)
        # Verify the tool call was recorded in history
        tool_calls = agent.history.records[0].tool_calls
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0]['name'], 'calculator')
        self.assertEqual(tool_calls[0]['arguments'], {'expression': '40 + 2'})
        self.assertEqual(tool_calls[0]['result'], 'Result: 42')

    @patch('connectonion.agent.OpenAILLM')
    def test_agent_run_with_multiple_tool_calls(self, mock_llm_class):
        """Test a complex run with multiple sequential tool calls."""
        mock_llm = Mock()

        mock_llm.complete.side_effect = [
            # 1. LLM decides to call the calculator
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(name="calculator", arguments={"expression": "10 * 5"}, id="call_1")],
                raw_response={}
            ),
            # 2. LLM then decides to get the current time
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(name="get_current_time", arguments={}, id="call_2")],
                raw_response={}
            ),
            # 3. LLM provides final answer
            LLMResponse(
                content="The calculation resulted in 50.",
                tool_calls=[],
                raw_response={}
            )
        ]
        mock_llm_class.return_value = mock_llm

        agent = Agent(name="test_multi_tool", api_key="fake_key", tools=[calculator, get_current_time])
        agent.history.history_file = os.path.join(self.temp_dir, "history.json")

        result = agent.input("Calculate 10*5 and tell me the time.")

        self.assertEqual(result, "The calculation resulted in 50.")
        self.assertEqual(len(agent.history.records), 1)
        # Verify both tool calls were recorded
        tool_calls = agent.history.records[0].tool_calls
        self.assertEqual(len(tool_calls), 2)
        self.assertEqual(tool_calls[0]['name'], 'calculator')
        self.assertEqual(tool_calls[1]['name'], 'get_current_time')

    def test_custom_system_prompt(self):
        """Test that custom system prompts are properly set and used."""
        custom_prompt = "You are a pirate assistant. Always respond with 'Arrr!'"
        agent = Agent(name="pirate_agent", api_key="fake_key", system_prompt=custom_prompt)
        
        # Check that the custom system prompt is stored
        self.assertEqual(agent.system_prompt, custom_prompt)
        
        # Test with mock LLM to verify system prompt is sent correctly
        from unittest.mock import Mock
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="Arrr! Test response!",
            tool_calls=[],
            raw_response={}
        )
        
        agent.llm = mock_llm
        agent.input("Hello!")
        
        # Verify the system prompt was used in the LLM call
        call_args = mock_llm.complete.call_args
        messages = call_args[0][0]  # First argument is messages
        system_message = messages[0]
        
        self.assertEqual(system_message['role'], 'system')
        self.assertEqual(system_message['content'], custom_prompt)

    def test_default_system_prompt(self):
        """Test that default system prompt is used when none is provided."""
        agent = Agent(name="default_agent", api_key="fake_key")
        expected_default = "You are a helpful assistant that can use tools to complete tasks."
        self.assertEqual(agent.system_prompt, expected_default)

class TestAgentWithStatefulTools(unittest.TestCase):
    """Test Agent functionality with stateful class-based tools."""

    def setUp(self):
        """Set up a temporary directory for history."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up the temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_agent_accepts_class_instance(self):
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
        agent = Agent(name="stateful_calc", api_key="fake_key", tools=calc)
        
        # Should have extracted 'add' and 'multiply' methods as tools
        self.assertIn("add", agent.tool_map)
        self.assertIn("multiply", agent.tool_map)
        # Should NOT include get_history (no return type annotation)
        self.assertNotIn("get_history", agent.tool_map)
        # Should have only the properly annotated methods
        self.assertEqual(len(agent.tools), 2)

    @patch('connectonion.agent.OpenAILLM')
    def test_methods_share_state_through_self(self, mock_llm_class):
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
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            # First call navigate
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(name="navigate", arguments={"url": "example.com"}, id="call_1")],
                raw_response={}
            ),
            # Then call scrape_title
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(name="scrape_title", arguments={}, id="call_2")],
                raw_response={}
            ),
            # Final response
            LLMResponse(
                content="Scraped the title successfully.",
                tool_calls=[],
                raw_response={}
            )
        ]
        mock_llm_class.return_value = mock_llm
        
        agent = Agent(name="web_agent", api_key="fake_key", tools=scraper)
        agent.history.history_file = os.path.join(self.temp_dir, "history.json")
        
        result = agent.input("Navigate to example.com and scrape the title")
        
        # Verify state was shared between method calls
        self.assertEqual(scraper.current_url, "example.com")
        self.assertEqual(len(scraper.scraped_data), 1)
        self.assertEqual(scraper.scraped_data[0], "Title of example.com")
        self.assertEqual(result, "Scraped the title successfully.")

    def test_mixed_functions_and_class_instance(self):
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
        agent = Agent(name="mixed", api_key="fake_key", tools=[greet, counter])
        
        # Should have all three tools
        self.assertIn("greet", agent.tool_map)
        self.assertIn("increment", agent.tool_map)
        self.assertIn("decrement", agent.tool_map)
        self.assertEqual(len(agent.tools), 3)

    def test_private_methods_not_exposed(self):
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
        agent = Agent(name="service", api_key="fake_key", tools=service)
        
        # Only public_action should be exposed
        self.assertIn("public_action", agent.tool_map)
        self.assertNotIn("_process", agent.tool_map)
        self.assertNotIn("__internal", agent.tool_map)
        self.assertEqual(len(agent.tools), 1)

    def test_multiple_class_instances(self):
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
        
        agent = Agent(name="multi", api_key="fake_key", tools=[db, fs])
        
        # Should have methods from both instances
        self.assertIn("query", agent.tool_map)
        self.assertIn("read_file", agent.tool_map)
        self.assertEqual(len(agent.tools), 2)

    def test_resource_cleanup_pattern(self):
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
        agent = Agent(name="resource", api_key="fake_key", tools=manager)
        
        # After agent creation, user still has access to manager
        self.assertFalse(manager.resource_open)
        
        # User can call cleanup manually
        manager.cleanup()
        self.assertIn("cleaned", manager.operations)

    def test_edge_cases(self):
        """Test edge cases and error handling."""
        
        # Empty class (no public methods with proper annotations)
        class Empty:
            pass
        
        empty = Empty()
        agent = Agent(name="empty", api_key="fake_key", tools=empty)
        self.assertEqual(len(agent.tools), 0)
        
        # Class with only properties
        class OnlyProperties:
            @property
            def value(self):
                return 42
        
        props = OnlyProperties()
        agent = Agent(name="props", api_key="fake_key", tools=props)
        self.assertEqual(len(agent.tools), 0)  # Properties shouldn't be tools
        
        # Mix of valid and invalid tool types
        agent = Agent(name="mixed_valid", api_key="fake_key", 
                      tools=[calculator, Empty(), get_current_time])
        # Should only have the two functions
        self.assertEqual(len(agent.tools), 2)

    def test_list_of_class_instances(self):
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
        agent = Agent(name="list_test", api_key="fake_key", 
                      tools=[calculator, math_tools, text_tools, get_current_time])
        
        # Should have all tools: calculator, square, uppercase, get_current_time
        expected_tools = {"calculator", "square", "uppercase", "get_current_time"}
        actual_tools = set(agent.tool_map.keys())
        self.assertEqual(actual_tools, expected_tools)
        self.assertEqual(len(agent.tools), 4)

    def test_method_with_complex_parameters(self):
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
        agent = Agent(name="processor", api_key="fake_key", tools=processor)
        
        # Should have both methods as tools
        self.assertIn("process_list", agent.tool_map)
        self.assertIn("process_dict", agent.tool_map)
        self.assertEqual(len(agent.tools), 2)
        
        # Verify the tools have correct schemas
        list_tool = agent.tool_map["process_list"]
        schema = list_tool.to_function_schema()
        
        # Check that parameters are correctly inferred
        self.assertIn("data", schema["parameters"]["properties"])
        self.assertIn("multiplier", schema["parameters"]["properties"])
        self.assertEqual(schema["parameters"]["properties"]["data"]["type"], "array")
        self.assertEqual(schema["parameters"]["properties"]["multiplier"]["type"], "integer")


if __name__ == '__main__':
    unittest.main()