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

        result = agent.run("Say hello")

        self.assertEqual(result, "Hello there! I am a test assistant.")
        # Verify history was recorded
        self.assertEqual(len(agent.history.records), 1)
        self.assertEqual(agent.history.records[0].task, "Say hello")
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

        result = agent.run("What is 40 + 2?")

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

        result = agent.run("Calculate 10*5 and tell me the time.")

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
        agent.run("Hello!")
        
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

if __name__ == '__main__':
    unittest.main()