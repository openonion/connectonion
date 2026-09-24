"""generate_image: a prompt goes in, one image file comes out.

The provider is faked at create_llm, so these pin what the tool does with a
response — where the bytes land, what the file is called, what it refuses —
and not whether Google answers. That is tests/e2e/real_api/test_real_gemini_image.py.
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from connectonion.core.llm import LLMResponse
from connectonion.useful_tools.generate_image import generate_image

IMAGE_BYTES = b"fake-image-bytes"
PNG_URL = "data:image/png;base64," + base64.b64encode(IMAGE_BYTES).decode()
JPEG_URL = "data:image/jpeg;base64," + base64.b64encode(IMAGE_BYTES).decode()


def _llm(images, content=None):
    llm = MagicMock()
    llm.complete.return_value = LLMResponse(content=content, tool_calls=[], raw_response=None, images=images)
    return llm


def _patched(llm):
    return patch("connectonion.useful_tools.generate_image.create_llm", return_value=llm)


def test_the_image_is_written_where_asked(tmp_path):
    out = tmp_path / "art" / "cat.png"
    with _patched(_llm([PNG_URL])):
        assert generate_image("a cat", save_to=str(out)) == str(out)
    assert out.read_bytes() == IMAGE_BYTES


def test_without_a_path_the_name_follows_the_format(tmp_path, monkeypatch):
    """gemini-3-pro-image-preview produces JPEG; a .png name would lie about it."""
    monkeypatch.chdir(tmp_path)
    with _patched(_llm([JPEG_URL])):
        result = generate_image("a cat")
    assert result.startswith("generated_image_") and result.endswith(".jpg")
    assert (tmp_path / result).read_bytes() == IMAGE_BYTES


def test_the_prompt_is_sent_as_one_user_message(tmp_path):
    llm = _llm([PNG_URL])
    with _patched(llm) as factory:
        generate_image("a fox", save_to=str(tmp_path / "fox.png"), model="gemini-3-pro-image-preview")
    assert factory.call_args.kwargs["model"] == "gemini-3-pro-image-preview"
    assert llm.complete.call_args.args[0] == [{"role": "user", "content": "a fox"}]


def test_a_reply_without_an_image_says_what_the_model_said_instead():
    with _patched(_llm([], content="I cannot draw that")):
        with pytest.raises(ValueError, match="I cannot draw that"):
            generate_image("a cat")


def test_a_managed_model_is_refused_before_any_request():
    """The co/ route has never been shown to return an image, so no call is made."""
    with _patched(_llm([PNG_URL])) as factory:
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            generate_image("a cat", model="co/gemini-2.5-flash-image")
    factory.assert_not_called()


def test_it_is_a_tool_an_agent_can_be_given():
    from connectonion.core.tool_factory import create_tool_from_function

    schema = create_tool_from_function(generate_image).to_function_schema()
    assert schema["name"] == "generate_image"
    assert "prompt" in schema["parameters"]["required"]
    assert "save_to" not in schema["parameters"]["required"]


def test_it_is_importable_from_the_package():
    import connectonion

    assert connectonion.generate_image is generate_image
    assert "generate_image" in connectonion.__all__
