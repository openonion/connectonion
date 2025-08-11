"""Verify the migration from run() to input() and task to user_prompt."""
import unittest
from unittest.mock import Mock, patch
import inspect
import tempfile
import os

from connectonion import Agent
from connectonion.history import BehaviorRecord
from connectonion.llm import LLMResponse, ToolCall


class TestInputMethodMigration(unittest.TestCase):
    """Test the input() method and user_prompt field migration."""
    
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_api_changes(self):
        """Verify API has changed from run() to input()."""
        agent = Agent(name="test", api_key="fake_key")
        
        # Check method existence
        self.assertTrue(hasattr(agent, 'input'), "Agent should have input() method")
        self.assertFalse(hasattr(agent, 'run'), "Agent should NOT have run() method")
        
        # Check method signature
        sig = inspect.signature(agent.input)
        params = list(sig.parameters.keys())
        self.assertIn('prompt', params, "input() should take 'prompt' parameter")
        self.assertEqual(sig.return_annotation, str, "input() should return str")
    
    def test_history_field_changes(self):
        """Verify history uses user_prompt instead of task."""
        sig = inspect.signature(BehaviorRecord.__init__)
        params = list(sig.parameters.keys())
        
        self.assertIn('user_prompt', params, "BehaviorRecord should have 'user_prompt'")
        self.assertNotIn('task', params, "BehaviorRecord should NOT have 'task'")
    
    @patch('connectonion.agent.OpenAILLM')
    def test_input_execution_and_history(self, mock_llm_class):
        """Test input() executes correctly and records user_prompt in history."""
        # Setup mock
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="Test response",
            tool_calls=[],
            raw_response={}
        )
        mock_llm_class.return_value = mock_llm
        
        # Execute
        agent = Agent(name="test", api_key="fake_key")
        agent.history.history_file = os.path.join(self.temp_dir, "history.json")
        
        test_prompt = "This is my test prompt"
        result = agent.input(test_prompt)
        
        # Verify execution
        self.assertEqual(result, "Test response")
        
        # Verify prompt was passed correctly
        messages = mock_llm.complete.call_args[0][0]
        user_msg = [m for m in messages if m['role'] == 'user'][0]
        self.assertEqual(user_msg['content'], test_prompt)
        
        # Verify history
        self.assertEqual(len(agent.history.records), 1)
        self.assertEqual(agent.history.records[0].user_prompt, test_prompt)
    
    @patch('connectonion.agent.OpenAILLM')
    def test_tool_integration(self, mock_llm_class):
        """Test tools work with input() method."""
        def calculator(expression: str) -> str:
            return str(eval(expression))
        
        # Setup mock with tool call
        mock_llm = Mock()
        mock_llm.complete.side_effect = [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id='1', name='calculator', arguments={'expression': '2+2'})],
                raw_response={}
            ),
            LLMResponse(content="The answer is 4", tool_calls=[], raw_response={})
        ]
        mock_llm_class.return_value = mock_llm
        
        # Execute
        agent = Agent(name="calc", api_key="fake", tools=[calculator])
        agent.history.history_file = os.path.join(self.temp_dir, "history.json")
        
        result = agent.input("What is 2+2?")
        
        # Verify
        self.assertIn("4", result)
        self.assertEqual(agent.history.records[0].user_prompt, "What is 2+2?")
        self.assertEqual(agent.history.records[0].tool_calls[0]['name'], 'calculator')


if __name__ == '__main__':
    unittest.main()