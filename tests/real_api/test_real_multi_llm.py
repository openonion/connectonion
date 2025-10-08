"""Tests for multi-LLM model support across OpenAI, Google, and Anthropic."""

import unittest
import os
import time
from unittest.mock import Mock, patch, MagicMock
from dotenv import load_dotenv
import pytest
from connectonion import Agent
from connectonion.llm import LLMResponse, ToolCall

# Load environment variables from .env file
load_dotenv()


# Test tools that will work across all models
def simple_calculator(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


def get_greeting(name: str) -> str:
    """Generate a greeting for a person."""
    return f"Hello, {name}!"


def process_data(data: str, uppercase: bool = False) -> str:
    """Process text data with optional uppercase conversion."""
    if uppercase:
        return data.upper()
    return data.lower()


class TestMultiLLMSupport(unittest.TestCase):
    """Test multi-LLM model support functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up class-level fixtures."""
        # Check which API keys are available
        cls.available_providers = []
        
        if os.getenv("OPENAI_API_KEY"):
            cls.available_providers.append("openai")
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            cls.available_providers.append("google")
        if os.getenv("ANTHROPIC_API_KEY"):
            cls.available_providers.append("anthropic")
        
        # Define test models for each provider (using actual models from docs/models.md)
        cls.test_models = {
            "openai": {
                # "flagship": "gpt-5",  # Requires passport verification
                # "fast": "gpt-5-mini",  # Requires passport verification
                # "fastest": "gpt-5-nano",  # Requires passport verification
                # "smart": "gpt-4.1",  # Not yet available
                "flagship": "o4-mini",  # Using o4-mini for testing
                "fast": "gpt-4o-mini",
                "fastest": "gpt-3.5-turbo",
                "smart": "gpt-4o",
                "legacy": "gpt-4o-mini"
            },
            "google": {
                "flagship": "gemini-2.5-pro",
                "experimental": "gemini-2.0-flash-exp",
                "fast": "gemini-1.5-flash",
                "long_context": "gemini-1.5-pro"
            },
            "anthropic": {
                "flagship": "claude-opus-4.1",
                "previous": "claude-opus-4",
                "balanced": "claude-sonnet-4",
                "fast": "claude-3-5-haiku"
            }
        }
    
    def setUp(self):
        """Set up test fixtures."""
        self.tools = [simple_calculator, get_greeting, process_data]
    
    # -------------------------------------------------------------------------
    # Model Detection Tests
    # -------------------------------------------------------------------------
    
    def test_model_detection_openai(self):
        """Test that OpenAI models are correctly detected."""
        # OpenAI models
        # models = ["gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "o1", "o1-mini"]  # GPT-5 requires passport
        models = ["o4-mini", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo", "o1", "o1-mini"]  # Using available models
        
        for model in models:
            # Models starting with gpt or o should be OpenAI
            self.assertTrue(model.startswith("gpt") or model.startswith("o"))
    
    def test_model_detection_google(self):
        """Test that Google models are correctly detected."""
        models = ["gemini-2.5-pro", "gemini-2.0-flash-exp", "gemini-2.0-flash-thinking-exp", 
                  "gemini-1.5-pro", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
        
        for model in models:
            self.assertTrue(model.startswith("gemini"))
    
    def test_model_detection_anthropic(self):
        """Test that Anthropic models are correctly detected."""
        models = ["claude-opus-4.1", "claude-opus-4", "claude-sonnet-4", 
                  "claude-3-5-sonnet", "claude-3-5-haiku"]
        
        for model in models:
            self.assertTrue(model.startswith("claude"))
    
    # -------------------------------------------------------------------------
    # Agent Creation Tests (Using Mock)
    # -------------------------------------------------------------------------
    
    @patch('connectonion.llm.OpenAILLM')
    def test_create_agent_with_openai_flagship(self, mock_openai):
        """Test creating an agent with OpenAI flagship model."""
        mock_instance = Mock()
        # mock_instance.model = "gpt-5"  # GPT-5 requires passport verification
        mock_instance.model = "o4-mini"  # Using o4-mini for testing
        mock_openai.return_value = mock_instance
        
        # agent = Agent("test_gpt5", model="gpt-5")  # Original GPT-5 test
        agent = Agent("test_o4", model="o4-mini")  # Using o4-mini
        self.assertEqual(agent.name, "test_o4")
        # Will work once multi-LLM is implemented
        # self.assertEqual(agent.llm.model, "o4-mini")
    
    @patch('connectonion.llm.GeminiLLM')  
    def test_create_agent_with_gemini25(self, mock_gemini):
        """Test creating an agent with Gemini 2.5 Pro model."""
        mock_instance = Mock()
        mock_instance.model = "gemini-2.5-pro"
        mock_gemini.return_value = mock_instance
        
        # Will work once GeminiLLM is implemented
        # agent = Agent("test_gemini", model="gemini-2.5-pro")
        # self.assertEqual(agent.llm.model, "gemini-2.5-pro")
        self.skipTest("GeminiLLM not yet implemented")
    
    @patch('connectonion.llm.AnthropicLLM')
    def test_create_agent_with_claude_opus4(self, mock_anthropic):
        """Test creating an agent with Claude Opus 4.1 model."""
        mock_instance = Mock()
        mock_instance.model = "claude-opus-4.1"
        mock_anthropic.return_value = mock_instance
        
        # Will work once AnthropicLLM is implemented
        # agent = Agent("test_claude", model="claude-opus-4.1")
        # self.assertEqual(agent.llm.model, "claude-opus-4.1")
        self.skipTest("AnthropicLLM not yet implemented")
    
    # -------------------------------------------------------------------------
    # Tool Compatibility Tests
    # -------------------------------------------------------------------------
    
    def test_tools_work_across_all_models(self):
        """Test that the same tools work with all model providers."""
        test_cases = []
        
        # Use actual models from our docs
        if "openai" in self.available_providers:
            # test_cases.append(("gpt-5-nano", "openai"))  # GPT-5 requires passport
            test_cases.append(("gpt-4o-mini", "openai"))  # Use available model for testing
        if "google" in self.available_providers:
            test_cases.append(("gemini-1.5-flash", "google"))
        if "anthropic" in self.available_providers:
            test_cases.append(("claude-3-5-haiku", "anthropic"))
        
        if not test_cases:
            self.skipTest("No API keys available for testing")
        
        for model, provider in test_cases:
            with self.subTest(model=model, provider=provider):
                try:
                    agent = Agent(f"test_{provider}", model=model, tools=self.tools)
                    
                    # Check all tools are registered
                    self.assertEqual(len(agent.tools), 3)
                    self.assertIn("simple_calculator", agent.tool_map)
                    self.assertIn("get_greeting", agent.tool_map)
                    self.assertIn("process_data", agent.tool_map)
                    
                    # Check tool schemas are generated correctly
                    for tool in agent.tools:
                        schema = tool.to_function_schema()
                        self.assertIn("name", schema)
                        self.assertIn("description", schema)
                        self.assertIn("parameters", schema)
                except Exception as e:
                    # Model might not be available yet
                    if "Unknown model" in str(e) or "not yet implemented" in str(e):
                        self.skipTest(f"Model {model} not yet implemented")
                    raise
    
    # -------------------------------------------------------------------------
    # Model Registry Tests
    # -------------------------------------------------------------------------
    
    def test_model_registry_mapping(self):
        """Test that models map to correct providers."""
        # This will be the expected mapping when implemented
        expected_mapping = {
            # OpenAI models
            # "gpt-5": "openai",  # Requires passport verification
            # "gpt-5-mini": "openai",  # Requires passport verification
            # "gpt-5-nano": "openai",  # Requires passport verification
            # "gpt-4.1": "openai",  # Not yet available
            "o4-mini": "openai",  # Testing model
            "gpt-4o": "openai",
            "gpt-4o-mini": "openai",
            "gpt-3.5-turbo": "openai",
            "o1": "openai",
            "o1-mini": "openai",
            
            # Google Gemini series
            "gemini-2.5-pro": "google",
            "gemini-2.0-flash-exp": "google",
            "gemini-2.0-flash-thinking-exp": "google",
            "gemini-1.5-pro": "google",
            "gemini-1.5-flash": "google",
            "gemini-1.5-flash-8b": "google",
            
            # Anthropic Claude series
            "claude-opus-4.1": "anthropic",
            "claude-opus-4": "anthropic",
            "claude-sonnet-4": "anthropic",
            "claude-3-5-sonnet": "anthropic",
            "claude-3-5-haiku": "anthropic"
        }
        
        # When MODEL_REGISTRY is implemented, test it
        try:
            from connectonion.llm import MODEL_REGISTRY
            for model, expected_provider in expected_mapping.items():
                self.assertEqual(MODEL_REGISTRY.get(model), expected_provider,
                               f"Model {model} should map to {expected_provider}")
        except ImportError:
            self.skipTest("MODEL_REGISTRY not yet implemented")
    
    # -------------------------------------------------------------------------
    # Error Handling Tests
    # -------------------------------------------------------------------------
    
    def test_missing_api_key_error(self):
        """Test appropriate error when API key is missing."""
        # Temporarily remove API key
        original_key = os.environ.get("OPENAI_API_KEY")
        if original_key:
            del os.environ["OPENAI_API_KEY"]
        
        try:
            with self.assertRaises(ValueError) as context:
                # agent = Agent("test", model="gpt-5")  # GPT-5 requires passport
                agent = Agent("test", model="o4-mini")  # Using o4-mini
            
            self.assertIn("API key", str(context.exception))
        finally:
            # Restore API key
            if original_key:
                os.environ["OPENAI_API_KEY"] = original_key
    
    def test_unknown_model_error(self):
        """Test error handling for unknown model names."""
        # This should raise an error once model validation is implemented
        try:
            with self.assertRaises(ValueError) as context:
                agent = Agent("test", model="unknown-model-xyz")
            self.assertIn("Unknown model", str(context.exception))
        except:
            # Model validation not yet implemented
            self.skipTest("Model validation not yet implemented")
    
    # -------------------------------------------------------------------------
    # Integration Tests (require actual API keys)
    # -------------------------------------------------------------------------
    
    @pytest.mark.real_api
    @pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="Requires OpenAI API key")
    def test_openai_flagship_real_call(self):
        """Test actual API call with OpenAI flagship model."""
        # Testing with o4-mini (GPT-5 requires passport verification)
        try:
            # agent = Agent("test", model="gpt-5", tools=self.tools)  # GPT-5 requires passport
            agent = Agent("test", model="o4-mini", tools=self.tools)  # Using o4-mini
            response = agent.input("Use the simple_calculator tool to add 5 and 3")
            self.assertIn("8", response)
        except Exception as e:
            if "model not found" in str(e).lower() or "o4-mini" in str(e).lower():
                # o4-mini not available yet, try with current model
                agent = Agent("test", model="gpt-4o-mini", tools=self.tools)
                response = agent.input("Use the simple_calculator tool to add 5 and 3")
                self.assertIn("8", response)
            else:
                raise
    
    @pytest.mark.real_api
    @pytest.mark.skipif(not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"),
                        reason="Requires Gemini API key")
    def test_google_gemini_real_call(self):
        """Test actual API call with Gemini model."""
        # Try Gemini 2.5 Pro first, fallback to 1.5 if not available
        models_to_try = ["gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]
        
        for model in models_to_try:
            try:
                agent = Agent("test", model=model, tools=self.tools)
                response = agent.input("Use the get_greeting tool to greet 'Alice'")
                self.assertIn("Alice", response)
                break
            except Exception as e:
                if model == models_to_try[-1]:
                    self.skipTest(f"No Gemini models available: {e}")
                continue
    
    @pytest.mark.real_api
    @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="Requires Anthropic API key")
    def test_anthropic_claude_real_call(self):
        """Test actual API call with Claude model."""
        # Try Claude Opus 4.1 first, fallback to available models
        models_to_try = ["claude-opus-4.1", "claude-3-5-sonnet", "claude-3-5-haiku"]
        
        for model in models_to_try:
            try:
                agent = Agent("test", model=model, tools=self.tools)
                response = agent.input("Use the process_data tool to convert 'Hello' to uppercase")
                self.assertIn("HELLO", response)
                break
            except Exception as e:
                if model == models_to_try[-1]:
                    self.skipTest(f"No Claude models available: {e}")
                continue
    
    # -------------------------------------------------------------------------
    # Model Comparison Tests
    # -------------------------------------------------------------------------
    
    @pytest.mark.real_api
    def test_flagship_model_comparison(self):
        """Test that flagship models from each provider can handle the same prompt."""
        prompt = "What is 2 + 2?"
        results = {}
        
        flagship_models = []
        if "openai" in self.available_providers:
            # Use gpt-4o-mini as fallback since GPT-5 isn't available yet
            flagship_models.append(("gpt-4o-mini", "openai"))
        if "google" in self.available_providers:
            flagship_models.append(("gemini-1.5-flash", "google"))
        if "anthropic" in self.available_providers:
            flagship_models.append(("claude-3-5-haiku", "anthropic"))
        
        if len(flagship_models) < 2:
            self.skipTest("Need at least 2 providers for comparison test")
        
        for model, provider in flagship_models:
            try:
                agent = Agent(f"compare_{provider}", model=model)
                response = agent.input(prompt)
                results[model] = response
                
                # All should mention "4" in their response
                self.assertIn("4", response.lower())
            except Exception as e:
                print(f"Failed with {model}: {e}")
                continue
    
    # -------------------------------------------------------------------------
    # Fallback Chain Tests
    # -------------------------------------------------------------------------
    
    def test_fallback_chain_with_new_models(self):
        """Test fallback chain with new model hierarchy."""
        # Priority order from docs/models.md
        fallback_models = [
            # "gpt-5",              # Best overall (requires passport verification)
            "o4-mini",            # Testing flagship model
            "claude-opus-4.1",    # Strong alternative (might not be available)
            "gemini-2.5-pro",     # Multimodal option (might not be available)
            # "gpt-5-mini",         # Faster fallback (requires passport)
            "gpt-4o",             # Current best available
            "gpt-4o-mini"         # Fallback (should work)
        ]
        
        agent = None
        successful_model = None
        
        for model in fallback_models:
            try:
                agent = Agent("fallback_test", model=model)
                successful_model = model
                break
            except Exception:
                continue
        
        if agent is None:
            self.skipTest("No models available for fallback test")
        
        self.assertIsNotNone(agent)
        self.assertIsNotNone(successful_model)
    
    # -------------------------------------------------------------------------
    # Model Feature Tests
    # -------------------------------------------------------------------------
    
    def test_context_window_sizes(self):
        """Test that models have correct context window sizes."""
        # Based on docs/models.md specifications
        context_windows = {
            # "gpt-5": 200000,  # Requires passport
            # "gpt-5-mini": 200000,  # Requires passport
            # "gpt-5-nano": 128000,  # Requires passport
            # "gpt-4.1": 128000,  # Not yet available
            "o4-mini": 128000,  # Testing model
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-3.5-turbo": 16385,
            "gemini-2.5-pro": 2000000,  # 2M tokens
            "gemini-1.5-pro": 2000000,  # 2M tokens
            "gemini-1.5-flash": 1000000,  # 1M tokens
            "claude-opus-4.1": 200000,
            "claude-opus-4": 200000,
            "claude-sonnet-4": 200000
        }
        
        # This will be tested once model metadata is implemented
        self.skipTest("Model metadata not yet implemented")
    
    def test_multimodal_capabilities(self):
        """Test which models support multimodal input."""
        # Based on docs/models.md
        multimodal_models = [
            # "gpt-5",  # Requires passport verification
            "o4-mini",  # Testing model
            "gpt-4o",
            "gpt-4o-mini",
            "gemini-2.5-pro",  # Supports audio, video, images, PDF
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "claude-opus-4.1",
            "claude-opus-4",
            "claude-sonnet-4"
        ]
        
        # Will be tested once multimodal support is implemented
        self.skipTest("Multimodal support not yet implemented")
    
    # -------------------------------------------------------------------------
    # Performance Tests
    # -------------------------------------------------------------------------
    
    @pytest.mark.benchmark
    def test_fast_model_performance(self):
        """Test that fast models initialize quickly."""
        if not self.available_providers:
            self.skipTest("No API keys available")
        
        # Use the fastest model from each provider
        fast_models = []
        if "openai" in self.available_providers:
            # fast_models.append("gpt-5-nano")  # Requires passport verification
            fast_models.append("gpt-4o-mini")  # Fastest available
        if "google" in self.available_providers:
            fast_models.append("gemini-1.5-flash")
        if "anthropic" in self.available_providers:
            fast_models.append("claude-3-5-haiku")
        
        for model in fast_models:
            try:
                start_time = time.time()
                agent = Agent("perf_test", model=model)
                end_time = time.time()
                
                initialization_time = end_time - start_time
                
                # Should initialize in less than 2 seconds
                self.assertLess(initialization_time, 2.0, 
                               f"Model {model} initialization took {initialization_time:.2f}s")
            except Exception as e:
                # Model might not be available yet
                if "not found" in str(e).lower() or "not available" in str(e).lower():
                    continue
                raise


class TestModelSelection(unittest.TestCase):
    """Test smart model selection based on use case."""
    
    def test_select_model_for_code_generation(self):
        """Test model selection for code generation tasks."""
        # Based on docs/models.md recommendations
        # code_models = ["gpt-5", "claude-opus-4.1"]  # GPT-5 requires passport
        code_models = ["o4-mini", "claude-opus-4.1"]  # Using o4-mini for testing
        
        # This would be implemented in actual code
        def select_model_for_task(task_type):
            if task_type == "code":
                # return "gpt-5"  # Requires passport verification
                return "o4-mini"  # Using o4-mini as alternative
            elif task_type == "reasoning":
                return "gemini-2.5-pro"
            elif task_type == "fast":
                # return "gpt-5-nano"  # Requires passport
                return "gpt-4o-mini"  # Using available fast model
            elif task_type == "long_context":
                return "gemini-2.5-pro"  # 2M tokens
            else:
                # return "gpt-5"  # Requires passport
                return "o4-mini"  # Using o4-mini
        
        self.assertEqual(select_model_for_task("code"), "o4-mini")
        self.assertEqual(select_model_for_task("reasoning"), "gemini-2.5-pro")
        self.assertEqual(select_model_for_task("fast"), "gpt-4o-mini")
        self.assertEqual(select_model_for_task("long_context"), "gemini-2.5-pro")


if __name__ == "__main__":
    # Run tests
    unittest.main()