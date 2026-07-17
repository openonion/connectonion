"""Real API tests for Gemini image models (Nano Banana family).

What it tests:
- co/gemini-3-pro-image-preview via OpenOnion managed keys (oo-api proxy)
- co/gemini-2.5-flash-image via OpenOnion managed keys
- gemini-2.5-flash-image via direct Gemini API key
- generate_image() one-shot tool end to end

Run with:
    export OPENONION_API_KEY=...   # or GEMINI_API_KEY for direct tests
    pytest tests/e2e/real_api/test_real_gemini_image.py -v -s

Costs money: ~$0.04 (nano banana) to ~$0.13 (nano banana pro) per image.

Known server status (verified 2026-07-17 against oo.openonion.ai):
    The co/ tests FAIL until oo-api adds image-model handling. oo-api currently
    forwards image models to Google's OpenAI-compatible chat.completions, which
    rejects them:
    - gemini-2.5-flash-image -> 400 "Image generation is not yet supported on
      the chat.completions endpoint for this model. Please use the standard
      client.images.generate method"
    - gemini-3-pro-image-preview -> 400 "Unhandled generated data mime type:
      image/jpeg" (Google compat layer can't serialize the generated JPEG)
    oo-api needs to either add a /v1/images/generations route or call Gemini's
    native generateContent for image models and return message.images.
"""

import base64
import os

import pytest

from connectonion.core.llm import create_llm
from connectonion.useful_tools.generate_image import generate_image

PROMPT = "A tiny watercolor illustration of a red fox sitting in snow"


def _assert_valid_image_response(response):
    assert response.images, (
        f"No images returned. content={response.content!r} "
        f"raw={getattr(response.raw_response, 'model_dump', lambda: response.raw_response)()}"
    )
    data_url = response.images[0]
    assert data_url.startswith("data:image/"), f"Not a data URL: {data_url[:80]}"
    _, _, b64_data = data_url.partition(",")
    image_bytes = base64.b64decode(b64_data)
    assert len(image_bytes) > 1000, "Decoded image suspiciously small"
    print(f"Got image: {len(image_bytes)} bytes, content={response.content!r}")


@pytest.mark.skipif(not os.getenv("OPENONION_API_KEY"), reason="OPENONION_API_KEY not set")
def test_co_gemini_3_pro_image_preview():
    """Nano Banana Pro via oo-api managed keys."""
    llm = create_llm("co/gemini-3-pro-image-preview")
    response = llm.complete([{"role": "user", "content": PROMPT}])
    _assert_valid_image_response(response)


@pytest.mark.skipif(not os.getenv("OPENONION_API_KEY"), reason="OPENONION_API_KEY not set")
def test_co_gemini_25_flash_image():
    """Nano Banana via oo-api managed keys."""
    llm = create_llm("co/gemini-2.5-flash-image")
    response = llm.complete([{"role": "user", "content": PROMPT}])
    _assert_valid_image_response(response)


@pytest.mark.skipif(not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")), reason="GEMINI_API_KEY not set")
def test_direct_gemini_25_flash_image():
    """Nano Banana via direct Gemini API (OpenAI-compatible endpoint)."""
    llm = create_llm("gemini-2.5-flash-image")
    response = llm.complete([{"role": "user", "content": PROMPT}])
    _assert_valid_image_response(response)


@pytest.mark.skipif(not os.getenv("OPENONION_API_KEY"), reason="OPENONION_API_KEY not set")
def test_generate_image_tool(tmp_path):
    """generate_image() end to end: prompt in, image file out."""
    path = generate_image(PROMPT, save_to=str(tmp_path / "fox.png"))
    saved = tmp_path / "fox.png"
    assert saved.exists()
    assert saved.stat().st_size > 1000
    print(f"Saved image to {path} ({saved.stat().st_size} bytes)")


@pytest.mark.skipif(not os.getenv("OPENONION_API_KEY"), reason="OPENONION_API_KEY not set")
def test_agent_captures_generated_images():
    """Agent.last_images should hold data URLs after an image-model response."""
    from connectonion import Agent

    agent = Agent("test-image-agent", model="co/gemini-3-pro-image-preview", quiet=True)
    result = agent.input(PROMPT)
    assert agent.last_images, f"No images captured. result={result!r}"
    assert agent.last_images[0].startswith("data:image/")
