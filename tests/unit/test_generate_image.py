"""Tests for the generate_image tool (Gemini image models).

What it tests:
- generate_image saves the returned data URL to disk and returns the path
- default filename generation and explicit save_to paths
- error when the model returns no image

Components under test:
- connectonion.useful_tools.generate_image
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from connectonion.core.llm import LLMResponse
from connectonion.useful_tools.generate_image import generate_image

PNG_BYTES = b"fake-png-bytes"
DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()


def _mock_llm(images, content=None):
    llm = MagicMock()
    llm.complete.return_value = LLMResponse(
        content=content, tool_calls=[], raw_response=None, images=images
    )
    return llm


def test_generate_image_saves_to_path(tmp_path):
    out = tmp_path / "art" / "cat.png"
    with patch("connectonion.useful_tools.generate_image.create_llm", return_value=_mock_llm([DATA_URL])):
        result = generate_image("a cat", save_to=str(out))

    assert result == str(out)
    assert out.read_bytes() == PNG_BYTES


def test_generate_image_default_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("connectonion.useful_tools.generate_image.create_llm", return_value=_mock_llm([DATA_URL])):
        result = generate_image("a cat")

    saved = tmp_path / result
    assert saved.exists()
    assert result.startswith("generated_image_")
    assert result.endswith(".png")
    assert saved.read_bytes() == PNG_BYTES


def test_generate_image_passes_prompt_and_model(tmp_path):
    llm = _mock_llm([DATA_URL])
    with patch("connectonion.useful_tools.generate_image.create_llm", return_value=llm) as factory:
        generate_image("a fox", save_to=str(tmp_path / "fox.png"), model="co/gemini-2.5-flash-image")

    assert factory.call_args.kwargs["model"] == "co/gemini-2.5-flash-image"
    messages = llm.complete.call_args.args[0]
    assert messages == [{"role": "user", "content": "a fox"}]


def test_generate_image_no_image_raises():
    with patch("connectonion.useful_tools.generate_image.create_llm", return_value=_mock_llm([], content="I cannot draw")):
        with pytest.raises(ValueError, match="returned no image"):
            generate_image("a cat")
