"""
Purpose: One-shot image generation using Gemini image models (Nano Banana family)
LLM-Note:
  Dependencies: imports from [base64, time, pathlib, core/llm.py] | imported by [useful_tools/__init__.py] | tested by [tests/unit/test_generate_image.py, tests/e2e/real_api/test_real_gemini_image.py]
  Data flow: user/agent calls generate_image(prompt, save_to, model) → create_llm(model) → llm.complete([user message]) → LLMResponse.images (data URLs) → decode base64 → write file → return saved path
  State/Effects: writes image file to disk | one LLM API request | no caching
  Integration: works as a direct function call AND as an agent tool (pass to Agent(tools=[generate_image])) | supports co/ managed keys and direct Gemini API keys
  Errors: raises ValueError if the model returns no image (includes text content for debugging) | provider errors bubble up from create_llm/complete

Generate images with Gemini image models.

Usage as a function:
    >>> from connectonion import generate_image
    >>> path = generate_image("a watercolor fox", save_to="fox.png")

Usage as an agent tool:
    >>> agent = Agent("artist", tools=[generate_image])
    >>> agent.input("Draw a watercolor fox and save it as fox.png")

Supported models:
    - co/gemini-3-pro-image-preview  (Nano Banana Pro, managed keys - default)
    - co/gemini-2.5-flash-image      (Nano Banana, managed keys)
    - gemini-3-pro-image-preview     (direct, needs GEMINI_API_KEY)
    - gemini-2.5-flash-image         (direct, needs GEMINI_API_KEY)
"""

import base64
import time
from pathlib import Path

from ..core.llm import create_llm

# data URL mime type -> file extension
_EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif"}


def generate_image(prompt: str, save_to: str = "", model: str = "co/gemini-3-pro-image-preview") -> str:
    """Generate an image from a text prompt and save it to a file.

    Args:
        prompt: Description of the image to generate.
        save_to: Output file path. Defaults to generated_image_<timestamp>.<ext>
            in the current directory.
        model: Image model to use. Default is co/gemini-3-pro-image-preview
            (managed keys). Also supports co/gemini-2.5-flash-image, or direct
            Gemini models like gemini-2.5-flash-image with GEMINI_API_KEY.

    Returns:
        Path of the saved image file.
    """
    llm = create_llm(model=model)
    response = llm.complete([{"role": "user", "content": prompt}])

    if not response.images:
        raise ValueError(
            f"Model '{model}' returned no image. "
            f"Text response: {response.content!r}"
        )

    data_url = response.images[0]
    header, _, b64_data = data_url.partition(",")
    mime_type = header.removeprefix("data:").split(";")[0] or "image/png"

    if save_to:
        path = Path(save_to)
    else:
        extension = _EXTENSIONS.get(mime_type, ".png")
        path = Path(f"generated_image_{int(time.time())}{extension}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(b64_data))
    return str(path)
