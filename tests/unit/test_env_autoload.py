"""Test .env auto-loading behavior.

This test verifies that the framework automatically loads .env files
from the current working directory without requiring users to call load_dotenv().

IMPORTANT: This test manipulates sys.modules and must run in ISOLATION.
Run with: pytest tests/unit/test_env_autoload.py -v
Skip in full suite to avoid affecting other tests.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pytest

# Skip these tests when run with full test suite (they modify sys.modules and pollute other tests)
# Run separately: pytest tests/unit/test_env_autoload.py -v
pytestmark = pytest.mark.skip(reason="Must run in isolation: pytest tests/unit/test_env_autoload.py -v")


class TestEnvAutoLoad(unittest.TestCase):
    """Test automatic .env file loading from current working directory."""

    def setUp(self):
        """Create temporary directory for isolated testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.temp_dir)

        # Save and clear environment variables
        self.original_env = {}
        env_vars_to_clear = [
            "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
            "OPENONION_API_KEY", "TEST_ENV_VAR", "AUTO_LOADED_VAR", "CUSTOM_VAR"
        ]
        for var in env_vars_to_clear:
            if var in os.environ:
                self.original_env[var] = os.environ[var]
                del os.environ[var]

        # Remove connectonion from sys.modules to force reimport
        self.modules_to_remove = [key for key in sys.modules if key.startswith('connectonion')]
        for module in self.modules_to_remove:
            del sys.modules[module]

    def tearDown(self):
        """Clean up temporary directory and restore original state."""
        os.chdir(self.original_cwd)
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

        # Restore original environment variables
        for var, value in self.original_env.items():
            os.environ[var] = value

    def test_env_loaded_from_current_directory(self):
        """Test that .env file is loaded from current working directory."""
        # Create .env file in temp directory
        env_file = Path(self.temp_dir) / ".env"
        env_file.write_text("TEST_ENV_VAR=test_value_123\n")

        # Import connectonion (triggers load_dotenv)
        import connectonion

        # Verify env var was loaded
        self.assertEqual(os.getenv("TEST_ENV_VAR"), "test_value_123")

    def test_openonion_api_key_loaded_from_env(self):
        """Test that OPENONION_API_KEY is available after framework import."""
        # Create .env with API key
        env_file = Path(self.temp_dir) / ".env"
        env_file.write_text("OPENONION_API_KEY=test_key_456\n")

        # Import framework
        import connectonion

        # Verify API key is in environment
        self.assertEqual(os.getenv("OPENONION_API_KEY"), "test_key_456")

    def test_openai_api_key_loaded_from_env(self):
        """Test that OPENAI_API_KEY is available for OpenAI provider."""
        # Create .env with OpenAI key
        env_file = Path(self.temp_dir) / ".env"
        env_file.write_text("OPENAI_API_KEY=sk-test-789\n")

        # Import framework
        import connectonion

        # Verify API key is in environment
        self.assertEqual(os.getenv("OPENAI_API_KEY"), "sk-test-789")

    def test_anthropic_api_key_loaded_from_env(self):
        """Test that ANTHROPIC_API_KEY is available for Anthropic provider."""
        # Create .env with Anthropic key
        env_file = Path(self.temp_dir) / ".env"
        env_file.write_text("ANTHROPIC_API_KEY=sk-ant-test-xyz\n")

        # Import framework
        import connectonion

        # Verify API key is in environment
        self.assertEqual(os.getenv("ANTHROPIC_API_KEY"), "sk-ant-test-xyz")

    def test_multiple_env_vars_loaded(self):
        """Test that multiple environment variables are loaded correctly."""
        # Create .env with multiple vars
        env_file = Path(self.temp_dir) / ".env"
        env_file.write_text(
            "OPENAI_API_KEY=sk-test-1\n"
            "ANTHROPIC_API_KEY=sk-ant-test-2\n"
            "OPENONION_API_KEY=test-3\n"
            "CUSTOM_VAR=custom_value\n"
        )

        # Import framework
        import connectonion

        # Verify all vars are loaded
        self.assertEqual(os.getenv("OPENAI_API_KEY"), "sk-test-1")
        self.assertEqual(os.getenv("ANTHROPIC_API_KEY"), "sk-ant-test-2")
        self.assertEqual(os.getenv("OPENONION_API_KEY"), "test-3")
        self.assertEqual(os.getenv("CUSTOM_VAR"), "custom_value")

    def test_no_manual_load_dotenv_required(self):
        """Test that users don't need to call load_dotenv() manually."""
        # Create .env file
        env_file = Path(self.temp_dir) / ".env"
        env_file.write_text("AUTO_LOADED_VAR=success\n")

        # Import connectonion WITHOUT calling load_dotenv()
        import connectonion
        from connectonion import Agent

        # Env var should already be loaded
        self.assertEqual(os.getenv("AUTO_LOADED_VAR"), "success")


class TestLLMProviderEnvVars(unittest.TestCase):
    """Test that each LLM provider checks its own env var correctly."""

    def test_openai_llm_uses_openai_api_key(self):
        """Test that OpenAILLM checks OPENAI_API_KEY env var."""
        from connectonion.core.llm import OpenAILLM

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            llm = OpenAILLM(model="gpt-4o")
            self.assertEqual(llm.api_key, "test-key")

    def test_anthropic_llm_uses_anthropic_api_key(self):
        """Test that AnthropicLLM checks ANTHROPIC_API_KEY env var."""
        from connectonion.core.llm import AnthropicLLM

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            llm = AnthropicLLM(model="claude-3-5-sonnet-20241022")
            self.assertEqual(llm.api_key, "test-key")

    def test_gemini_llm_uses_google_api_key(self):
        """Test that GeminiLLM checks GOOGLE_API_KEY env var."""
        from connectonion.core.llm import GeminiLLM

        # Save original values (GeminiLLM checks both GEMINI_API_KEY and GOOGLE_API_KEY)
        original_gemini = os.environ.get("GEMINI_API_KEY")
        original_google = os.environ.get("GOOGLE_API_KEY")
        try:
            # Clear GEMINI_API_KEY and set GOOGLE_API_KEY
            os.environ.pop("GEMINI_API_KEY", None)
            os.environ["GOOGLE_API_KEY"] = "test-key"
            llm = GeminiLLM(model="gemini-2.0-flash-exp")
            self.assertEqual(llm.api_key, "test-key")
        finally:
            # Restore original values
            if original_gemini:
                os.environ["GEMINI_API_KEY"] = original_gemini
            if original_google:
                os.environ["GOOGLE_API_KEY"] = original_google
            else:
                os.environ.pop("GOOGLE_API_KEY", None)

    def test_openonion_llm_uses_openonion_api_key(self):
        """Test that OpenOnionLLM checks OPENONION_API_KEY env var."""
        from connectonion.core.llm import OpenOnionLLM

        with patch.dict(os.environ, {"OPENONION_API_KEY": "test-key"}):
            llm = OpenOnionLLM(model="co/gpt-5")
            self.assertEqual(llm.auth_token, "test-key")

    def test_explicit_api_key_overrides_env(self):
        """Test that explicit api_key parameter overrides env var."""
        from connectonion.core.llm import OpenAILLM

        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
            llm = OpenAILLM(api_key="explicit-key", model="gpt-4o")
            self.assertEqual(llm.api_key, "explicit-key")


if __name__ == "__main__":
    unittest.main()
