"""
Purpose: One-shot image generation with a Gemini image model: prompt in, image file out
LLM-Note:
  Dependencies: imports from [base64, time, pathlib, core/llm.py] | imported by [useful_tools/__init__.py, __init__.py (lazy)] | tested by [tests/unit/test_generate_image.py, tests/e2e/real_api/test_real_gemini_image.py]
  Data flow: generate_image(prompt, save_to, model) → create_llm(model) → llm.complete([user message]) → LLMResponse.images (data URLs) → base64-decode the first → write file → return the saved path
  State/Effects: writes one image file (creating parent directories) | one provider request | no caching
  Integration: plain function and agent tool (Agent(tools=[generate_image])) | direct Gemini keys (GEMINI_API_KEY) or OpenRouter (openrouter/google/...) | co/ managed models are refused up front, see _MANAGED_NOT_SUPPORTED
  Errors: ValueError for a co/ model or a response with no image (carries the model's text) | provider errors bubble from create_llm/complete
"""

import base64
import time
from pathlib import Path

from ..core.llm import create_llm

_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}

# The managed route was tried in July 2026 and did not work: oo-api forwarded
# image models to Google's chat.completions, which refuses them. Nothing since
# shows it does, so a co/ model fails here with a sentence that says what to
# use instead, rather than with a provider 400 three layers down.
_MANAGED_NOT_SUPPORTED = (
    "generate_image does not support co/ managed models yet: the managed "
    "backend has not been shown to return images. Use a direct Gemini image "
    "model such as 'gemini-2.5-flash-image' with GEMINI_API_KEY set."
)


def generate_image(prompt: str, save_to: str = "", model: str = "gemini-2.5-flash-image") -> str:
    """Generate an image from a text prompt and save it to a file.

    Args:
        prompt: Description of the image to generate.
        save_to: Output file path. Defaults to generated_image_<timestamp>.<ext>
            in the current directory.
        model: Gemini image model. Default gemini-2.5-flash-image with your own
            GEMINI_API_KEY; gemini-3-pro-image-preview routes the same way.

    Returns:
        Path of the saved image file.
    """
    if model.startswith("co/"):
        raise ValueError(_MANAGED_NOT_SUPPORTED)

    response = create_llm(model=model).complete([{"role": "user", "content": prompt}])
    if not response.images:
        raise ValueError(f"Model '{model}' returned no image. Text response: {response.content!r}")

    header, _, b64_data = response.images[0].partition(",")
    mime_type = header.removeprefix("data:").split(";")[0]
    path = Path(save_to) if save_to else Path(
        f"generated_image_{int(time.time())}{_EXTENSIONS.get(mime_type, '.png')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(b64_data))
    return str(path)
