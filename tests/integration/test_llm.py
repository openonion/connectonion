"""Tests for LLM functionality including multi-LLM support."""

import unittest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dotenv import load_dotenv
import pytest
from pydantic import BaseModel, ValidationError
from typing import Optional

# Load environment variables from tests/.env
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
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
    
    @patch('openai.OpenAI')
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
    
    @patch('openai.OpenAI')
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
    
    @patch('openai.OpenAI')
    def test_system_prompt_as_string(self, mock_openai_class):
        """Test using a string system prompt."""
        self.skipTest("Need to update mocking for new implementation")
        
        mock_llm = Mock()
        mock_llm.complete.return_value = Mock(content="Translated", tool_calls=[])
        mock_llm_class.return_value = mock_llm
        
        from connectonion import llm_do
        result = llm_do(
            "Hello",
            system_prompt="You are a translator. Translate to Spanish."
        )
        
        # Verify the prompt was included in the system message
        call_args = mock_llm.complete.call_args[0][0]  # messages
        system_msg = call_args[0]
        self.assertEqual(system_msg["role"], "system")
        self.assertIn("translator", system_msg["content"])
    
    def test_system_prompt_as_file(self):
        """Test loading system prompt from file."""
        self.skipTest("Need to update mocking for new implementation")
        
        # Create a temporary prompt file
        prompt_file = Path(self.temp_dir) / "test_prompt.md"
        prompt_file.write_text("You are a helpful assistant.")
        
        with patch('openai.OpenAI') as mock_openai_class:
            mock_llm = Mock()
            mock_llm.complete.return_value = Mock(content="Response", tool_calls=[])
            mock_openai_class.return_value = mock_llm
            
            from connectonion import llm_do
            result = llm_do("Test", system_prompt=str(prompt_file))
            
            # Verify file content was loaded
            call_args = mock_llm.complete.call_args[0][0]
            system_msg = call_args[0]
            self.assertIn("helpful assistant", system_msg["content"])
    
    @patch('openai.OpenAI')
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
    
    @patch('openai.OpenAI')
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
        
        with patch('openai.OpenAI') as mock_openai_class:
            mock_llm = Mock()
            # Return invalid JSON for the model
            mock_llm.complete.return_value = Mock(
                content='{"wrong": "fields"}',
                tool_calls=[]
            )
            mock_openai_class.return_value = mock_llm
            
            from connectonion import llm_do
            with self.assertRaises(ValidationError):
                llm_do("Extract", output=SimpleModel)
    
    def test_system_prompt_file_not_found(self):
        """Test error when system prompt file doesn't exist."""
        self.skipTest("Waiting for implementation")
        
        from connectonion import llm_do
        with self.assertRaises(FileNotFoundError):
            llm_do("Test", system_prompt="nonexistent_file.md")
    
    def test_api_error_handling(self):
        """Test handling of API errors."""
        self.skipTest("Waiting for implementation")
        
        with patch('openai.OpenAI') as mock_openai_class:
            mock_llm = Mock()
            mock_llm.complete.side_effect = Exception("API Error")
            mock_openai_class.return_value = mock_llm
            
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
    def test_real_api_with_system_prompt(self):
        """Test real API with custom system prompt."""
        if not self.api_key:
            self.skipTest("OPENAI_API_KEY not found")
        
        from connectonion import llm_do
        result = llm_do(
            "Bonjour",
            system_prompt="You are a translator. Translate from French to English only. Be concise."
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
        
        with patch('openai.OpenAI') as mock_openai_class:
            mock_llm = Mock()
            mock_llm.complete.return_value = Mock(
                content='{"summary": "Test summary", "word_count": 10}',
                tool_calls=[]
            )
            mock_openai_class.return_value = mock_llm
            
            agent = Agent("test", tools=[analyze_text])
            # This would need more mocking for the agent's LLM calls
            self.assertIsNotNone(agent)
    
    def test_complex_nested_model(self):
        """Test with complex nested Pydantic model."""
        self.skipTest("Waiting for implementation")
        
        with patch('openai.OpenAI') as mock_openai_class:
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
            mock_openai_class.return_value = mock_llm
            
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
        
        with patch('openai.OpenAI') as mock_openai_class:
            mock_llm = Mock()
            mock_llm.complete.return_value = Mock(content="Summary", tool_calls=[])
            mock_openai_class.return_value = mock_llm
            
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
            with patch('openai.OpenAI') as mock_openai_class:
                mock_llm = Mock()
                mock_llm.complete.return_value = Mock(
                    content=f"Response {index}",
                    tool_calls=[]
                )
                mock_openai_class.return_value = mock_llm
                
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


class TestMultiLLMSupport(unittest.TestCase):
    """Test multi-LLM support across OpenAI, Anthropic, and Google."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.has_openai = bool(os.getenv("OPENAI_API_KEY"))
        self.has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
        self.has_google = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    
    @pytest.mark.real_api
    def test_openai_model(self):
        """Test OpenAI model integration."""
        if not self.has_openai:
            self.skipTest("OPENAI_API_KEY not found")
        
        from connectonion import Agent
        agent = Agent("test_openai", model="gpt-4o-mini")
        response = agent.input("Say hello in 5 words or less")
        
        self.assertIsNotNone(response)
        self.assertIsInstance(response, str)
        self.assertTrue(len(response.split()) <= 10)  # Allow some flexibility
    
    @pytest.mark.real_api
    def test_anthropic_model(self):
        """Test Anthropic Claude model integration."""
        if not self.has_anthropic:
            self.skipTest("ANTHROPIC_API_KEY not found")
        
        from connectonion import Agent
        agent = Agent("test_anthropic", model="claude-3-5-haiku-20241022")
        response = agent.input("Say hello in 5 words or less")
        
        self.assertIsNotNone(response)
        self.assertIsInstance(response, str)
    
    @pytest.mark.real_api
    def test_google_gemini_model(self):
        """Test Google Gemini model integration."""
        if not self.has_google:
            self.skipTest("GEMINI_API_KEY not found")
        
        from connectonion import Agent
        agent = Agent("test_gemini", model="gemini-1.5-flash")
        response = agent.input("Say hello in 5 words or less")
        
        self.assertIsNotNone(response)
        self.assertIsInstance(response, str)
    
    @pytest.mark.real_api
    def test_tool_use_across_models(self):
        """Test tool use functionality across different LLM providers."""
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b
        
        # Test OpenAI with tools
        if self.has_openai:
            from connectonion import Agent
            agent = Agent("openai_tools", model="gpt-4o-mini", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            self.assertIn("42", str(response))
        
        # Test Anthropic with tools
        if self.has_anthropic:
            from connectonion import Agent
            agent = Agent("anthropic_tools", model="claude-3-5-haiku-20241022", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            self.assertIn("42", str(response))
        
        # Test Gemini with tools
        if self.has_google:
            from connectonion import Agent
            agent = Agent("gemini_tools", model="gemini-1.5-flash", tools=[add_numbers])
            response = agent.input("What is 25 plus 17?")
            self.assertIn("42", str(response))
    
    def test_model_registry(self):
        """Test that model registry correctly maps models to providers."""
        from connectonion.llm import MODEL_REGISTRY
        
        # Test OpenAI models
        self.assertEqual(MODEL_REGISTRY["gpt-4o"], "openai")
        self.assertEqual(MODEL_REGISTRY["gpt-4o-mini"], "openai")
        self.assertEqual(MODEL_REGISTRY["o1"], "openai")
        self.assertEqual(MODEL_REGISTRY["o4-mini"], "openai")
        
        # Test Anthropic models
        self.assertEqual(MODEL_REGISTRY["claude-3-5-sonnet-20241022"], "anthropic")
        self.assertEqual(MODEL_REGISTRY["claude-3-5-haiku-20241022"], "anthropic")
        self.assertEqual(MODEL_REGISTRY["claude-opus-4.1"], "anthropic")
        
        # Test Google models
        self.assertEqual(MODEL_REGISTRY["gemini-2.0-flash-exp"], "google")
        self.assertEqual(MODEL_REGISTRY["gemini-1.5-pro"], "google")
        self.assertEqual(MODEL_REGISTRY["gemini-1.5-flash"], "google")
    
    def test_create_llm_factory(self):
        """Test the create_llm factory function."""
        from connectonion.llm import create_llm, OpenAILLM, AnthropicLLM, GeminiLLM
        
        # Test OpenAI model creation
        if self.has_openai:
            llm = create_llm("gpt-4o-mini")
            self.assertIsInstance(llm, OpenAILLM)
        
        # Test Anthropic model creation
        if self.has_anthropic:
            llm = create_llm("claude-3-5-haiku-20241022")
            self.assertIsInstance(llm, AnthropicLLM)
        
        # Test Google model creation
        if self.has_google:
            llm = create_llm("gemini-1.5-flash")
            self.assertIsInstance(llm, GeminiLLM)
    
    def test_model_inference_from_name(self):
        """Test that model provider is correctly inferred from model name."""
        from connectonion.llm import create_llm
        
        # Test inference for models not in registry
        if self.has_openai:
            llm = create_llm("gpt-new-model-xyz")  # Starts with 'gpt'
            from connectonion.llm import OpenAILLM
            self.assertIsInstance(llm, OpenAILLM)
        
        if self.has_anthropic:
            llm = create_llm("claude-future-model")  # Starts with 'claude'
            from connectonion.llm import AnthropicLLM
            self.assertIsInstance(llm, AnthropicLLM)
        
        if self.has_google:
            llm = create_llm("gemini-next-gen")  # Starts with 'gemini'
            from connectonion.llm import GeminiLLM
            self.assertIsInstance(llm, GeminiLLM)


class TestGeminiTools(unittest.TestCase):
    """Test Google Gemini tool calling specifically."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.has_google = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    
    @pytest.mark.real_api
    def test_gemini_simple_tool_call(self):
        """Test simple tool call with Gemini."""
        if not self.has_google:
            self.skipTest("GEMINI_API_KEY not found")
        
        from connectonion import Agent
        
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b
        
        agent = Agent("gemini_calc", model="gemini-1.5-flash", tools=[add_numbers])
        response = agent.input("What is 15 plus 27? Please use the add_numbers tool.")
        
        self.assertIsNotNone(response)
        self.assertIn("42", str(response))
    
    @pytest.mark.real_api
    def test_gemini_multiple_tools(self):
        """Test Gemini with multiple tools available."""
        if not self.has_google:
            self.skipTest("GEMINI_API_KEY not found")
        
        from connectonion import Agent
        
        def add_numbers(a: int, b: int) -> int:
            """Add two numbers together."""
            return a + b
        
        def multiply_numbers(x: float, y: float) -> float:
            """Multiply two numbers."""
            return x * y
        
        agent = Agent("gemini_multi", model="gemini-1.5-flash", 
                     tools=[add_numbers, multiply_numbers])
        response = agent.input("First add 10 and 20, then multiply 5 by 6. Use the tools.")
        
        self.assertIsNotNone(response)
        # Should mention both results
        response_str = str(response)
        self.assertTrue("30" in response_str or "30.0" in response_str)
        self.assertTrue("30" in response_str or "30.0" in response_str)
    
    @pytest.mark.real_api
    def test_gemini_without_tools(self):
        """Test Gemini response without tools."""
        if not self.has_google:
            self.skipTest("GEMINI_API_KEY not found")
        
        from connectonion import Agent
        agent = Agent("gemini_chat", model="gemini-1.5-flash")
        response = agent.input("What is the capital of France?")
        
        self.assertIsNotNone(response)
        self.assertIn("Paris", response)


if __name__ == "__main__":
    unittest.main()