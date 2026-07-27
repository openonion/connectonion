"""Read a local image into the multimodal data-URL format used by agents."""

import base64
import mimetypes
from pathlib import Path


IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def read_image(path: str) -> str:
    """Read an image so a vision-capable model can inspect it.

    Args:
        path: Path to a PNG, JPEG, GIF, or WebP image.

    Returns:
        A data URL consumed by the image_result_formatter plugin, or an
        actionable error string when the path cannot be read as an image.
    """
    image_path = Path(path)
    if not image_path.exists():
        return f"Error: File '{path}' does not exist"
    if not image_path.is_file():
        return f"Error: '{path}' is not a file"

    extension = image_path.suffix.lower()
    if extension not in IMAGE_MIME_TYPES:
        supported = ", ".join(sorted(IMAGE_MIME_TYPES))
        return (
            f"Error: unsupported image format '{extension or 'none'}'. "
            f"Supported formats: {supported}"
        )

    mime = mimetypes.guess_type(str(image_path))[0] or IMAGE_MIME_TYPES[extension]
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"
