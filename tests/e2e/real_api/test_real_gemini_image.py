"""Gemini image models against the real providers.

Nothing in the unit suite shows a provider returns an image; this is the file
that would. It has not been run for the port from branch
claude/gemini-image-models-p8dfbb, so treat the direct and OpenRouter paths as
unverified until it passes once with real keys.

    export GEMINI_API_KEY=...        # direct tests
    export OPENROUTER_API_KEY=...    # OpenRouter test
    pytest tests/e2e/real_api/test_real_gemini_image.py -v -s

Costs money: one image per test.

What the July 2026 branch observed, and why the code is shaped this way:

- Google's OpenAI-compatible chat.completions refused both image models:
  gemini-2.5-flash-image -> 400 "Image generation is not yet supported on the
  chat.completions endpoint for this model. Please use the standard
  client.images.generate method"; gemini-3-pro-image-preview -> 400
  "Unhandled generated data mime type: image/jpeg". GeminiLLM therefore uses
  images.generate for image models called without tools.
- The co/ managed route forwarded to that same chat.completions and failed the
  same way. There is no co/ test here on purpose: generate_image refuses co/
  models, and OpenOnionLLM does not ask for image output.
"""

import base64
import os

import pytest

from connectonion.core.llm import create_llm
from connectonion.useful_tools.generate_image import generate_image

pytestmark = pytest.mark.real_api

PROMPT = "A tiny watercolor illustration of a red fox sitting in snow"
HAS_GEMINI = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _assert_image(response):
    assert response.images, f"No images returned. content={response.content!r}"
    header, _, b64_data = response.images[0].partition(",")
    assert header.startswith("data:image/"), header
    assert len(base64.b64decode(b64_data)) > 1000, "decoded image suspiciously small"


@pytest.mark.skipif(not HAS_GEMINI, reason="GEMINI_API_KEY not set")
@pytest.mark.parametrize("model", ["gemini-2.5-flash-image", "gemini-3-pro-image-preview"])
def test_direct_gemini_image_model(model):
    _assert_image(create_llm(model).complete([{"role": "user", "content": PROMPT}]))


@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set")
def test_openrouter_gemini_image_model():
    llm = create_llm("openrouter/google/gemini-2.5-flash-image")
    _assert_image(llm.complete([{"role": "user", "content": PROMPT}]))


@pytest.mark.skipif(not HAS_GEMINI, reason="GEMINI_API_KEY not set")
def test_generate_image_writes_a_file(tmp_path):
    path = generate_image(PROMPT, save_to=str(tmp_path / "fox.png"))
    assert os.path.getsize(path) > 1000


@pytest.mark.skipif(not HAS_GEMINI, reason="GEMINI_API_KEY not set")
def test_an_agent_on_an_image_model_keeps_the_image():
    from connectonion import Agent

    agent = Agent("artist", model="gemini-2.5-flash-image", log=False, quiet=True)
    agent.input(PROMPT)
    assert agent.last_images and agent.last_images[0].startswith("data:image/")
