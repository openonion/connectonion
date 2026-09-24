"""Image-output models come back as LLMResponse.images; text calls do not change.

Ported from branch claude/gemini-image-models-p8dfbb. Every provider client
here is a fake: the request each class *sends* and what it *does* with a reply
are what is pinned. Whether Google or OpenRouter actually answer that request
with an image is not established by any test in this file.

The second half is the guard the port needed most: a text model must see the
exact request it saw before, and a text reply must parse to the same content.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from connectonion.core.llm import (
    GeminiLLM,
    LLMResponse,
    OpenOnionLLM,
    OpenRouterLLM,
    _data_url,
    _extract_images,
    _extract_text,
    is_image_model,
)

PNG_B64 = "iVBORw0KGgoAAAANSUhEUg=="
JPEG_B64 = "/9j/4AAQSkZJRgABAQ=="


def _chat_response(message):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, prompt_tokens_details=None),
    )


def _text_message(text="hello"):
    return SimpleNamespace(content=text, tool_calls=None)


class TestWhichModelsAreImageModels:

    @pytest.mark.parametrize("model", [
        "gemini-2.5-flash-image",
        "gemini-3-pro-image-preview",
        "co/gemini-3-pro-image-preview",
        "openrouter/google/gemini-2.5-flash-image",
        "google/gemini-2.5-flash-image",
    ])
    def test_image_variants_are(self, model):
        assert is_image_model(model)

    @pytest.mark.parametrize("model", [
        "gemini-3.8-flash", "co/gemini-2.5-pro", "gemini-2.5-flash-lite", "o4-mini",
        "claude-sonnet-4", "dall-e-3", "gpt-image-1",
    ])
    def test_everything_else_is_not(self, model):
        assert not is_image_model(model)


class TestDirectGeminiImageModels:

    def _llm(self, model, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        llm = GeminiLLM(model=model)
        llm.client = MagicMock()
        return llm

    def test_an_image_model_goes_to_the_images_api(self, monkeypatch):
        llm = self._llm("gemini-2.5-flash-image", monkeypatch)
        llm.client.images.generate.return_value = SimpleNamespace(data=[SimpleNamespace(b64_json=PNG_B64)])

        response = llm.complete([
            {"role": "user", "content": "first turn"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "draw a cat"},
        ])

        assert response.images == [f"data:image/png;base64,{PNG_B64}"]
        assert response.content is None and response.tool_calls == [] and response.usage is None
        sent = llm.client.images.generate.call_args.kwargs
        assert sent == {"model": "gemini-2.5-flash-image", "prompt": "draw a cat",
                        "response_format": "b64_json", "n": 1}
        llm.client.chat.completions.create.assert_not_called()

    def test_jpeg_output_is_labelled_jpeg(self, monkeypatch):
        llm = self._llm("gemini-3-pro-image-preview", monkeypatch)
        llm.client.images.generate.return_value = SimpleNamespace(data=[SimpleNamespace(b64_json=JPEG_B64)])

        response = llm.complete([{"role": "user", "content": "draw a cat"}])

        assert response.images == [f"data:image/jpeg;base64,{JPEG_B64}"]

    def test_with_tools_it_stays_on_chat_rather_than_dropping_them(self, monkeypatch):
        llm = self._llm("gemini-2.5-flash-image", monkeypatch)
        llm.client.chat.completions.create.return_value = _chat_response(_text_message())
        tool = {"name": "t", "description": "d", "parameters": {"type": "object", "properties": {}}}

        llm.complete([{"role": "user", "content": "hi"}], tools=[tool])

        llm.client.images.generate.assert_not_called()
        assert llm.client.chat.completions.create.call_args.kwargs["tools"]

    def test_a_text_model_sends_the_same_request_as_before(self, monkeypatch):
        llm = self._llm("gemini-3.8-flash", monkeypatch)
        llm.client.chat.completions.create.return_value = _chat_response(_text_message("hello"))

        response = llm.complete([{"role": "user", "content": "hi"}])

        assert llm.client.chat.completions.create.call_args.kwargs == {
            "model": "gemini-3.8-flash", "messages": [{"role": "user", "content": "hi"}]}
        assert response.content == "hello"
        assert response.images == []
        llm.client.images.generate.assert_not_called()


class TestOpenRouterImageModels:

    def _llm(self, model, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        llm = OpenRouterLLM(model=model)
        llm.client = MagicMock()
        return llm

    def test_an_image_model_asks_for_the_image_modality_and_gets_images(self, monkeypatch):
        llm = self._llm("openrouter/google/gemini-2.5-flash-image", monkeypatch)
        url = f"data:image/png;base64,{PNG_B64}"
        message = SimpleNamespace(content="Here it is", tool_calls=None,
                                  images=[{"type": "image_url", "image_url": {"url": url}}])
        llm.client.chat.completions.create.return_value = _chat_response(message)

        response = llm.complete([{"role": "user", "content": "draw a cat"}])

        assert llm.client.chat.completions.create.call_args.kwargs["modalities"] == ["text", "image"]
        assert response.images == [url]
        assert response.content == "Here it is"

    def test_a_text_model_is_not_sent_modalities(self, monkeypatch):
        llm = self._llm("openrouter/openai/o4-mini", monkeypatch)
        llm.client.chat.completions.create.return_value = _chat_response(_text_message("hello"))

        response = llm.complete([{"role": "user", "content": "hi"}])

        assert "modalities" not in llm.client.chat.completions.create.call_args.kwargs
        assert response.content == "hello" and response.images == []


class TestManagedRouteIsUntouched:
    """co/ image output was never shown to work, so this port does not ask for it."""

    def test_a_managed_image_model_sends_no_modalities(self, monkeypatch):
        llm = OpenOnionLLM(api_key="token", model="co/gemini-3-pro-image-preview")
        llm.client = MagicMock()
        llm.client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=_text_message("hi"))], usage=None)

        response = llm.complete([{"role": "user", "content": "draw"}])

        assert "modalities" not in llm.client.chat.completions.create.call_args.kwargs
        assert response.images == []


class TestParsingReplies:

    def test_images_inside_content_parts_are_found(self):
        url = f"data:image/png;base64,{PNG_B64}"
        message = SimpleNamespace(images=None, content=[
            {"type": "text", "text": "Here you go"},
            {"type": "image_url", "image_url": {"url": url}},
        ])
        assert _extract_images(message) == [url]
        assert _extract_text(message) == "Here you go"

    def test_a_string_reply_is_returned_untouched(self):
        message = SimpleNamespace(content="  exact text  ")
        assert _extract_text(message) == "  exact text  "
        assert _extract_images(message) == []

    def test_unknown_bytes_default_to_png(self):
        assert _data_url("AAAA").startswith("data:image/png;base64,")

    def test_a_response_built_without_images_has_an_empty_list(self):
        assert LLMResponse(content="x", tool_calls=[], raw_response=None).images == []


class TestTheAgentKeepsTheImages:

    class _ImageLLM:
        model = "gemini-2.5-flash-image"

        def __init__(self, images):
            self.images = images

        def complete(self, messages, tools=None, **kwargs):
            content = None if self.images else "hi"
            return LLMResponse(content=content, tool_calls=[], raw_response=None, images=self.images)

    def test_images_land_on_last_images_and_reach_the_client(self):
        from connectonion import Agent

        url = f"data:image/png;base64,{PNG_B64}"
        agent = Agent("artist", llm=self._ImageLLM([url]), log=False, quiet=True)
        agent.io = MagicMock()

        result = agent.input("draw a cat")

        # An image-only answer used to hit the empty-terminal RuntimeError.
        assert result == "Generated 1 image."

        assert agent.last_images == [url]
        agent.io.send_image.assert_called_once_with(url)

    def test_a_text_reply_leaves_last_images_empty(self):
        from connectonion import Agent

        agent = Agent("writer", llm=self._ImageLLM([]), log=False, quiet=True)
        agent.input("hello")

        assert agent.last_images == []
