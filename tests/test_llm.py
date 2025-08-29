"""Tests for the llm_do() one-shot function."""

import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dotenv import load_dotenv
import pytest
from pydantic import BaseModel, ValidationError
from typing import Optional

# Load environment variables
load_dotenv()

# Import will be updated when implementation is ready
# from connectonion import llm_do


# Test models for structured output
class SimpleModel(BaseModel):
    """Simple test model."""
    value: str
    count: int


class Analysis(BaseModel):
    """Test analysis model."""
    sentiment: str
    confidence: float
    keywords: list[str]


class ComplexModel(BaseModel):
    """Complex nested model for testing."""
    title: str
    metadata: dict
    items: list[str]
    score: Optional[float] = None


class TestLLMFunction(unittest.TestCase):
    """Test the llm_do() one-shot function."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.api_key = os.getenv("OPENAI_API_KEY")
        
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    # -------------------------------------------------------------------------
    # Basic Functionality Tests (Mocked)
    # -------------------------------------------------------------------------
    
    @patch('connectonion.llm_function.openai.OpenAI')
    def test_simple_string_input_output(self, mock_openai_class):
        """Test basic string input returns string output."""
        # Skip until we update mocking
        self.skipTest("Need to update mocking for new implementation")
        
        # Mock the LLM response
        mock_llm = Mock()
        mock_llm.complete.return_value = Mock(content="4", tool_calls=[])
        mock_llm_class.return_value = mock_llm
        
        from connectonion import llm_do
        result = llm_do("What's 2+2?")
        
        self.assertEqual(result, "4")
        mock_llm.complete.assert_called_once()
    
    @patch('connectonion.llm_function.openai.OpenAI')
    def test_structured_output_with_pydantic(self, mock_openai_class):
        """Test structured output using Pydantic model."""
        self.skipTest("Need to update mocking for new implementation")
        
        # Mock LLM to return JSON that matches the model
        mock_llm = Mock()
        mock_llm.complete.return_value = Mock(
            content='{"value": "test", "count": 42}',
            tool_calls=[]
        )
        mock_llm_class.return_value = mock_llm
        
        from connectonion import llm_do
        result = llm_do("Extract data", output=SimpleModel)
        
        self.assertIsInstance(result, SimpleModel)
        self.assertEqual(result.value, "test")
        self.assertEqual(result.count, 42)
    
    @patch('connectonion.llm_function.openai.OpenAI')
    def test_prompt_as_string(self, mock_openai_class):
        """Test using a string prompt."""
        self.skipTest("Need to update mocking for new implementation")
        
        mock_llm = Mock()
        mock_llm.complete.return_value = Mock(content="Translated", tool_calls=[])
        mock_llm_class.return_value = mock_llm
        
        from connectonion import llm_do
        result = llm_do(
            "Hello",
            prompt="You are a translator. Translate to Spanish."
        )
        
        # Verify the prompt was included in the system message
        call_args = mock_llm.complete.call_args[0][0]  # messages
        system_msg = call_args[0]
        self.assertEqual(system_msg["role"], "system")
        self.assertIn("translator", system_msg["content"])
    
    def test_prompt_as_file(self):
        """Test loading prompt from file."""
        self.skipTest("Need to update mocking for new implementation")
        
        # Create a temporary prompt file
        prompt_file = Path(self.temp_dir) / "test_prompt.md"
        prompt_file.write_text("You are a helpful assistant.")
        
        with patch('connectonion.llm_function.OpenAILLM') as mock_llm_class:
            mock_llm = Mock()
            mock_llm.complete.return_value = Mock(content="Response", tool_calls=[])
            mock_llm_class.return_value = mock_llm
            
            from connectonion import llm_do
            result = llm_do("Test", prompt=str(prompt_file))
            
            # Verify file content was loaded
            call_args = mock_llm.complete.call_args[0][0]
            system_msg = call_args[0]
            self.assertIn("helpful assistant", system_msg["content"])
    
    @patch('connectonion.llm_function.openai.OpenAI')
    def test_custom_model_parameter(self, mock_openai_class):
        """Test using custom model parameter."""
        self.skipTest("Need to update mocking for new implementation")
        
        from connectonion import llm_do
        result = llm_do("Test", model="gpt-4")
        
        # Verify model was passed to OpenAILLM
        mock_llm_class.assert_called_with(
            api_key=unittest.mock.ANY,
            model="gpt-4"
        )
    
    @patch('connectonion.llm_function.openai.OpenAI')
    def test_temperature_parameter(self, mock_openai_class):
        """Test temperature parameter affects LLM call."""
        self.skipTest("Need to update mocking for new implementation")
        
        mock_llm = Mock()
        mock_llm.complete.return_value = Mock(content="Creative", tool_calls=[])
        mock_llm_class.return_value = mock_llm
        
        from connectonion import llm_do
        result = llm_do("Write a poem", temperature=1.5)
        
        # Temperature should be passed through to the LLM call
        # This would depend on implementation details
        self.assertEqual(result, "Creative")
    
    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------
    
    def test_invalid_pydantic_model_output(self):
        """Test handling when LLM output doesn't match Pydantic model."""
        self.skipTest("Waiting for implementation")
        
        with patch('connectonion.llm_function.OpenAILLM') as mock_llm_class:
            mock_llm = Mock()
            # Return invalid JSON for the model
            mock_llm.complete.return_value = Mock(
                content='{"wrong": "fields"}',
                tool_calls=[]
            )
            mock_llm_class.return_value = mock_llm
            
            from connectonion import llm_do
            with self.assertRaises(ValidationError):
                llm_do("Extract", output=SimpleModel)
    
    def test_prompt_file_not_found(self):
        """Test error when prompt file doesn't exist."""
        self.skipTest("Waiting for implementation")
        
        from connectonion import llm_do
        with self.assertRaises(FileNotFoundError):
            llm_do("Test", prompt="nonexistent_file.md")
    
    def test_api_error_handling(self):
        """Test handling of API errors."""
        self.skipTest("Waiting for implementation")
        
        with patch('connectonion.llm_function.OpenAILLM') as mock_llm_class:
            mock_llm = Mock()
            mock_llm.complete.side_effect = Exception("API Error")
            mock_llm_class.return_value = mock_llm
            
            from connectonion import llm_do
            with self.assertRaises(Exception) as ctx:
                llm_do("Test")
            self.assertIn("API Error", str(ctx.exception))
    
    # -------------------------------------------------------------------------
    # Real API Tests (marked for separate execution)
    # -------------------------------------------------------------------------
    
    @pytest.mark.real_api
    def test_real_api_simple_call(self):
        """Test real API call with simple string."""
        if not self.api_key:
            self.skipTest("OPENAI_API_KEY not found")
        
        from connectonion import llm_do
        result = llm_do("What is 2+2? Reply with just the number.")
        
        self.assertIsNotNone(result)
        self.assertIn("4", result)
    
    @pytest.mark.real_api
    def test_real_api_structured_output(self):
        """Test real API with structured Pydantic output."""
        if not self.api_key:
            self.skipTest("OPENAI_API_KEY not found")
        
        from connectonion import llm_do
        
        class TestResult(BaseModel):
            answer: int
            explanation: str
        
        result = llm_do(
            "What is 10 times 5?",
            output=TestResult
        )
        
        self.assertIsInstance(result, TestResult)
        self.assertEqual(result.answer, 50)
        self.assertIsNotNone(result.explanation)
    
    @pytest.mark.real_api
    def test_real_api_with_prompt(self):
        """Test real API with custom prompt."""
        if not self.api_key:
            self.skipTest("OPENAI_API_KEY not found")
        
        from connectonion import llm_do
        result = llm_do(
            "Bonjour",
            prompt="You are a translator. Translate from French to English only. Be concise."
        )
        
        self.assertIsNotNone(result)
        # Check for common translations
        result_lower = result.lower()
        self.assertTrue("hello" in result_lower or "good" in result_lower)
    
    # -------------------------------------------------------------------------
    # Integration Tests
    # -------------------------------------------------------------------------
    
    def test_llm_function_in_agent_tool(self):
        """Test using llm_do() inside an Agent tool."""
        self.skipTest("Waiting for implementation")
        
        from connectonion import Agent, llm
        
        def analyze_text(text: str) -> str:
            """Tool that uses llm_do() internally."""
            class Result(BaseModel):
                summary: str
                word_count: int
            
            analysis = llm_do(f"Analyze: {text}", output=Result)
            return f"Summary: {analysis.summary} ({analysis.word_count} words)"
        
        with patch('connectonion.llm_function.OpenAILLM') as mock_llm_class:
            mock_llm = Mock()
            mock_llm.complete.return_value = Mock(
                content='{"summary": "Test summary", "word_count": 10}',
                tool_calls=[]
            )
            mock_llm_class.return_value = mock_llm
            
            agent = Agent("test", tools=[analyze_text])
            # This would need more mocking for the agent's LLM calls
            self.assertIsNotNone(agent)
    
    def test_complex_nested_model(self):
        """Test with complex nested Pydantic model."""
        self.skipTest("Waiting for implementation")
        
        with patch('connectonion.llm_function.OpenAILLM') as mock_llm_class:
            mock_llm = Mock()
            mock_llm.complete.return_value = Mock(
                content='''{
                    "title": "Test",
                    "metadata": {"key": "value"},
                    "items": ["a", "b", "c"],
                    "score": 0.95
                }''',
                tool_calls=[]
            )
            mock_llm_class.return_value = mock_llm
            
            from connectonion import llm_do
            result = llm_do("Generate complex data", output=ComplexModel)
            
            self.assertIsInstance(result, ComplexModel)
            self.assertEqual(result.title, "Test")
            self.assertEqual(result.metadata["key"], "value")
            self.assertEqual(len(result.items), 3)
            self.assertEqual(result.score, 0.95)
    
    # -------------------------------------------------------------------------
    # Performance and Edge Cases
    # -------------------------------------------------------------------------
    
    def test_empty_input(self):
        """Test handling of empty input."""
        from connectonion import llm_do
        with self.assertRaises(ValueError):
            llm_do("")
    
    def test_very_long_input(self):
        """Test handling of very long input."""
        self.skipTest("Waiting for implementation")
        
        with patch('connectonion.llm_function.OpenAILLM') as mock_llm_class:
            mock_llm = Mock()
            mock_llm.complete.return_value = Mock(content="Summary", tool_calls=[])
            mock_llm_class.return_value = mock_llm
            
            from connectonion import llm_do
            long_text = "word " * 10000  # Very long input
            result = llm_do(long_text)
            
            self.assertEqual(result, "Summary")
    
    def test_concurrent_calls(self):
        """Test thread safety of concurrent llm_do() calls."""
        self.skipTest("Waiting for implementation")
        
        import threading
        from connectonion import llm_do
        
        results = []
        
        def make_call(prompt, index):
            with patch('connectonion.llm_function.OpenAILLM') as mock_llm_class:
                mock_llm = Mock()
                mock_llm.complete.return_value = Mock(
                    content=f"Response {index}",
                    tool_calls=[]
                )
                mock_llm_class.return_value = mock_llm
                
                result = llm_do(prompt)
                results.append(result)
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=make_call, args=(f"Test {i}", i))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        self.assertEqual(len(results), 5)


if __name__ == "__main__":
    unittest.main()