"""Tests for LLM functionality including multi-LLM support."""

"""
LLM-Note: Integration tests for LLM multi-provider support

What it tests:
- test_llm_do_empty_input: Error handling for empty input
- TestMultiLLMSupport: Multi-LLM provider integration
  - test_model_registry: Model-to-provider mapping
  - test_create_llm_factory: LLM factory function for all providers

Components under test:
- connectonion.llm_do (one-shot LLM function)
- connectonion.core.llm.MODEL_REGISTRY
- connectonion.core.llm.create_llm (factory pattern)
- OpenAILLM, AnthropicLLM, GeminiLLM
"""

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

        # Test Google image models (Nano Banana family)
        assert MODEL_REGISTRY["gemini-2.5-flash-image"] == "google"
        assert MODEL_REGISTRY["gemini-2.5-flash-image-preview"] == "google"

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


class TestImageModels:
    """Test Gemini image-output model support (Nano Banana family)."""

    def test_is_image_model(self):
        from connectonion.core.llm import is_image_model

        assert is_image_model("gemini-2.5-flash-image")
        assert is_image_model("gemini-2.5-flash-image-preview")
        assert is_image_model("gemini-3-pro-image-preview")
        assert is_image_model("co/gemini-2.5-flash-image")
        assert is_image_model("co/gemini-3-pro-image-preview")
        assert is_image_model("google/gemini-2.5-flash-image")  # OpenRouter style

        assert not is_image_model("gemini-2.5-flash")
        assert not is_image_model("co/gemini-2.5-pro")
        assert not is_image_model("gpt-4o")
        assert not is_image_model("dall-e-3")  # not a gemini model

    def _make_image_response(self, message):
        """Build a mock chat.completions response around the given message."""
        from unittest.mock import MagicMock

        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        response.usage.prompt_tokens = 10
        response.usage.completion_tokens = 1290
        response.usage.prompt_tokens_details = None
        return response

    def test_gemini_image_model_uses_images_api(self, monkeypatch):
        """GeminiLLM routes image models through images.generate.

        Google's OpenAI-compatible layer rejects image models on
        chat.completions ("Image generation is not yet supported on the
        chat.completions endpoint ... use client.images.generate").
        """
        from unittest.mock import MagicMock
        from connectonion.core.llm import GeminiLLM

        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        llm = GeminiLLM(model="gemini-2.5-flash-image")

        image_item = MagicMock()
        image_item.b64_json = "aGVsbG8="
        images_response = MagicMock()
        images_response.data = [image_item]

        llm.client = MagicMock()
        llm.client.images.generate = MagicMock(return_value=images_response)

        response = llm.complete([{"role": "user", "content": "draw a cat"}])

        assert response.images == ["data:image/png;base64,aGVsbG8="]
        assert response.tool_calls == []
        call_kwargs = llm.client.images.generate.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-flash-image"
        assert call_kwargs["prompt"] == "draw a cat"
        assert call_kwargs["response_format"] == "b64_json"
        llm.client.chat.completions.create.assert_not_called()

    def test_gemini_text_model_uses_chat_completions(self, monkeypatch):
        """Non-image models keep using chat.completions."""
        from unittest.mock import MagicMock
        from connectonion.core.llm import GeminiLLM

        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        llm = GeminiLLM(model="gemini-2.5-flash")

        message = MagicMock()
        message.content = "hello"
        message.tool_calls = None
        message.images = None

        mock_create = MagicMock(return_value=self._make_image_response(message))
        llm.client = MagicMock()
        llm.client.chat.completions.create = mock_create

        response = llm.complete([{"role": "user", "content": "hi"}])

        assert response.images == []
        assert response.content == "hello"
        llm.client.images.generate.assert_not_called()

    def test_openonion_complete_returns_images(self, monkeypatch):
        """OpenOnionLLM (co/ managed keys) should surface generated images."""
        from unittest.mock import MagicMock
        from connectonion.core.llm import OpenOnionLLM

        monkeypatch.setenv("OPENONION_API_KEY", "test-token")
        llm = OpenOnionLLM(model="co/gemini-3-pro-image-preview")

        data_url = "data:image/png;base64,aGVsbG8="
        message = MagicMock()
        message.content = None
        message.tool_calls = None
        message.images = [{"type": "image_url", "image_url": {"url": data_url}}]

        mock_create = MagicMock(return_value=self._make_image_response(message))
        llm.client = MagicMock()
        llm.client.chat.completions.create = mock_create

        response = llm.complete([{"role": "user", "content": "draw a cat"}])

        assert response.images == [data_url]
        assert mock_create.call_args.kwargs["model"] == "gemini-3-pro-image-preview"
        assert mock_create.call_args.kwargs["modalities"] == ["text", "image"]

    def test_extract_images_from_multimodal_content(self):
        """Images embedded as multimodal content parts should also be extracted."""
        from unittest.mock import MagicMock
        from connectonion.core.llm import _extract_images, _extract_text

        data_url = "data:image/png;base64,aGVsbG8="
        message = MagicMock()
        message.images = None
        message.content = [
            {"type": "text", "text": "Here you go"},
            {"type": "image_url", "image_url": {"url": data_url}},
        ]

        assert _extract_images(message) == [data_url]
        assert _extract_text(message) == "Here you go"
