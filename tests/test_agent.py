"""Basic tests for ConnectOnion Agent."""

import unittest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch
from connectonion import Agent
from connectonion.tools import Calculator, CurrentTime, ReadFile
from connectonion.llm import LLMResponse, ToolCall


class TestTools(unittest.TestCase):
    """Test built-in tools."""
    
    def test_calculator(self):
        calc = Calculator()
        self.assertEqual(calc.run(expression="2 + 2"), "Result: 4")
        self.assertEqual(calc.run(expression="10 * 5"), "Result: 50")
        self.assertEqual(calc.run(expression="2 ** 3"), "Result: 8")
        self.assertIn("Error", calc.run(expression="invalid"))
    
    def test_current_time(self):
        time_tool = CurrentTime()
        result = time_tool.run()
        self.assertTrue(len(result) > 0)
        self.assertNotIn("Error", result)
    
    def test_read_file(self):
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Test content")
            temp_path = f.name
        
        try:
            read_tool = ReadFile()
            result = read_tool.run(filepath=temp_path)
            self.assertEqual(result, "Test content")
            
            # Test non-existent file
            result = read_tool.run(filepath="/path/that/does/not/exist")
            self.assertIn("Error", result)
        finally:
            os.unlink(temp_path)


class TestAgent(unittest.TestCase):
    """Test Agent functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)
    
    def test_agent_creation(self):
        """Test agent can be created."""
        agent = Agent(name="test_agent", api_key="fake_key")
        self.assertEqual(agent.name, "test_agent")
        self.assertEqual(len(agent.tools), 0)
    
    def test_agent_with_tools(self):
        """Test agent with tools."""
        tools = [Calculator(), CurrentTime()]
        agent = Agent(name="test_agent", api_key="fake_key", tools=tools)
        self.assertEqual(len(agent.tools), 2)
        self.assertIn("calculator", agent.tool_map)
        self.assertIn("current_time", agent.tool_map)
    
    def test_add_remove_tools(self):
        """Test adding and removing tools."""
        agent = Agent(name="test_agent", api_key="fake_key")
        
        # Add tool
        calc = Calculator()
        agent.add_tool(calc)
        self.assertIn("calculator", agent.list_tools())
        
        # Remove tool
        agent.remove_tool("calculator")
        self.assertNotIn("calculator", agent.list_tools())
    
    @patch('connectonion.agent.OpenAILLM')
    def test_agent_run_without_tools(self, mock_llm_class):
        """Test agent running task without tool calls."""
        # Mock LLM response
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="Hello! I'm a helpful assistant.",
            tool_calls=[],
            raw_response=None
        )
        mock_llm_class.return_value = mock_llm
        
        # Use unique agent name with temp directory
        agent = Agent(name="test_agent_solo", api_key="fake_key")
        agent.history.save_dir = self.temp_dir  # Use temp directory
        agent.history.history_file = self.temp_dir + "/behavior.json"
        agent.history.records = []  # Clear any existing records
        
        result = agent.run("Say hello")
        
        self.assertEqual(result, "Hello! I'm a helpful assistant.")
        self.assertEqual(len(agent.history.records), 1)
        self.assertEqual(agent.history.records[0].task, "Say hello")
    
    @patch('connectonion.agent.OpenAILLM')
    def test_agent_run_with_tools(self, mock_llm_class):
        """Test agent running task with tool calls."""
        # Mock LLM responses
        mock_llm = Mock()
        
        # First response: request tool call
        mock_llm.complete.side_effect = [
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(
                    name="calculator",
                    arguments={"expression": "2 + 2"},
                    id="call_123"
                )],
                raw_response=None
            ),
            # Second response: final answer
            LLMResponse(
                content="The result is 4.",
                tool_calls=[],
                raw_response=None
            )
        ]
        mock_llm_class.return_value = mock_llm
        
        # Use unique agent name with temp directory
        agent = Agent(name="test_agent_tools", api_key="fake_key", tools=[Calculator()])
        agent.history.save_dir = self.temp_dir  # Use temp directory  
        agent.history.history_file = self.temp_dir + "/behavior2.json"
        agent.history.records = []  # Clear any existing records
        
        result = agent.run("What is 2 + 2?")
        
        self.assertEqual(result, "The result is 4.")
        self.assertEqual(len(agent.history.records), 1)
        self.assertEqual(len(agent.history.records[0].tool_calls), 1)
        self.assertEqual(agent.history.records[0].tool_calls[0]['name'], 'calculator')


if __name__ == '__main__':
    unittest.main()