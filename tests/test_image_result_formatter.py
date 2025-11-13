"""Tests for image_result_formatter plugin"""

import pytest
from connectonion.useful_plugins.image_result_formatter import _is_base64_image


class TestIsBase64Image:
    """Test base64 image detection logic"""

    def test_data_url_png(self):
        """Should detect PNG data URL"""
        # Tiny 1x1 red PNG
        data_url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="

        is_img, mime, data = _is_base64_image(data_url)

        assert is_img is True
        assert mime == "image/png"
        assert data == "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="

    def test_data_url_jpeg(self):
        """Should detect JPEG data URL"""
        data_url = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAIBAQIBAQICAgICAgICAwUDAwMDAwYEBAMFBwYHBw=="

        is_img, mime, data = _is_base64_image(data_url)

        assert is_img is True
        assert mime == "image/jpeg"
        assert "/9j/4AAQSkZJRgABAQEAYABgAAD" in data

    def test_data_url_in_mixed_content(self):
        """Should detect data URL even when mixed with other text"""
        mixed = "Screenshot saved! Here's the data: data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="

        is_img, mime, data = _is_base64_image(mixed)

        assert is_img is True
        assert mime == "image/png"

    def test_long_plain_base64(self):
        """Should detect long plain base64 string (>100 chars)"""
        # Create a base64 string longer than 100 characters
        long_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg==" * 2

        is_img, mime, data = _is_base64_image(long_base64)

        assert is_img is True
        assert mime == "image/png"  # Defaults to PNG
        assert data == long_base64.strip()

    def test_short_base64_not_detected(self):
        """Should NOT detect short base64-like strings (<100 chars)"""
        short_base64 = "ABC123DEF456GHI789"

        is_img, mime, data = _is_base64_image(short_base64)

        assert is_img is False

    def test_regular_text_not_detected(self):
        """Should NOT detect regular text"""
        text = "This is just regular text, not an image at all"

        is_img, mime, data = _is_base64_image(text)

        assert is_img is False

    def test_non_string_input(self):
        """Should handle non-string input gracefully"""
        is_img, mime, data = _is_base64_image(123)

        assert is_img is False
        assert mime == ""
        assert data == ""

    def test_empty_string(self):
        """Should handle empty string"""
        is_img, mime, data = _is_base64_image("")

        assert is_img is False

    def test_webp_data_url(self):
        """Should detect WebP data URL"""
        data_url = "data:image/webp;base64,UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAwA0JaQAA3AA/vuUAAA="

        is_img, mime, data = _is_base64_image(data_url)

        assert is_img is True
        assert mime == "image/webp"
