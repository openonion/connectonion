import base64

from connectonion.useful_tools.read_image import read_image


def test_read_image_returns_data_url(tmp_path):
    image = tmp_path / "shot.webp"
    payload = b"RIFFfake-webp"
    image.write_bytes(payload)

    result = read_image(str(image))

    assert result.startswith("data:image/webp;base64,")
    assert base64.b64decode(result.split(",", 1)[1]) == payload


def test_read_image_rejects_missing_file(tmp_path):
    path = tmp_path / "missing.png"
    assert read_image(str(path)) == f"Error: File '{path}' does not exist"


def test_read_image_rejects_directory(tmp_path):
    assert read_image(str(tmp_path)) == f"Error: '{tmp_path}' is not a file"


def test_read_image_rejects_unsupported_format(tmp_path):
    image = tmp_path / "shot.bmp"
    image.write_bytes(b"BM")

    result = read_image(str(image))

    assert result.startswith("Error: unsupported image format '.bmp'")
    assert ".png" in result
