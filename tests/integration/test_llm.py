"""Tests for LLM functionality including multi-LLM support."""

import os

import pytest


def test_llm_do_empty_input():
    """Test handling of empty input."""
    from connectonion import llm_do

    with pytest.raises(ValueError):
        llm_do("")


class TestMultiLLMSupport:
    """Test multi-LLM support across OpenAI, Anthropic, and Google."""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        """Set up test fixtures."""
        self.has_openai = bool(os.getenv("OPENAI_API_KEY"))
        self.has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))
        self.has_google = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))

    def test_model_registry(self):
        """Test that model registry correctly maps models to providers."""
        from connectonion.core.llm import MODEL_REGISTRY

        # Test OpenAI models
        assert MODEL_REGISTRY["gpt-4o"] == "openai"
        assert MODEL_REGISTRY["gpt-4o-mini"] == "openai"
        assert MODEL_REGISTRY["o1"] == "openai"
        assert MODEL_REGISTRY["o4-mini"] == "openai"

        # Test Anthropic models
        assert MODEL_REGISTRY["claude-3-5-sonnet-20241022"] == "anthropic"
        assert MODEL_REGISTRY["claude-3-5-haiku-20241022"] == "anthropic"
        assert MODEL_REGISTRY["claude-opus-4.1"] == "anthropic"

        # Test Google models
        assert MODEL_REGISTRY["gemini-3-pro-preview"] == "google"
        assert MODEL_REGISTRY["gemini-3-pro-image-preview"] == "google"
        assert MODEL_REGISTRY["gemini-2.5-flash"] == "google"

    def test_create_llm_factory(self):
        """Test the create_llm factory function."""
        from connectonion.core.llm import create_llm, OpenAILLM, AnthropicLLM, GeminiLLM

        # Test OpenAI model creation
        if self.has_openai:
            llm = create_llm("gpt-4o-mini")
            assert isinstance(llm, OpenAILLM)

        # Test Anthropic model creation
        if self.has_anthropic:
            llm = create_llm("claude-3-5-haiku-20241022")
            assert isinstance(llm, AnthropicLLM)

        # Test Google model creation
        if self.has_google:
            llm = create_llm("gemini-2.5-flash")
            assert isinstance(llm, GeminiLLM)

    def test_model_inference_from_name(self):
        """Test that model provider is correctly inferred from model name."""
        from connectonion.core.llm import create_llm

        # Test inference for models not in registry
        if self.has_openai:
            llm = create_llm("gpt-new-model-xyz")  # Starts with 'gpt'
            from connectonion.core.llm import OpenAILLM
            assert isinstance(llm, OpenAILLM)

        if self.has_anthropic:
            llm = create_llm("claude-future-model")  # Starts with 'claude'
            from connectonion.core.llm import AnthropicLLM
            assert isinstance(llm, AnthropicLLM)

        if self.has_google:
            llm = create_llm("gemini-next-gen")  # Starts with 'gemini'
            from connectonion.core.llm import GeminiLLM
            assert isinstance(llm, GeminiLLM)
