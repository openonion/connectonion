"""Unit tests for DiffWriter."""

import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from connectonion.useful_tools.diff_writer import DiffWriter


class TestDiffWriterAutoApprove:
    """Tests for DiffWriter with auto_approve=True (no user interaction)."""

    def test_write_new_file(self):
        """Write a new file with auto-approve."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=True)
            test_file = os.path.join(tmpdir, "test.py")

            result = writer.write(test_file, "print('hello')")

            assert "Wrote" in result
            assert Path(test_file).exists()
            assert Path(test_file).read_text() == "print('hello')"

    def test_write_creates_parent_directories(self):
        """Write creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=True)
            test_file = os.path.join(tmpdir, "nested", "deep", "test.py")

            result = writer.write(test_file, "content")

            assert Path(test_file).exists()
            assert Path(test_file).read_text() == "content"

    def test_write_overwrites_existing_file(self):
        """Write overwrites existing file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=True)
            test_file = os.path.join(tmpdir, "test.py")

            # Create initial file
            Path(test_file).write_text("original")

            # Overwrite
            result = writer.write(test_file, "new content")

            assert Path(test_file).read_text() == "new content"

    def test_write_returns_byte_count(self):
        """Write returns the number of bytes written."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=True)
            test_file = os.path.join(tmpdir, "test.py")
            content = "hello world"

            result = writer.write(test_file, content)

            assert f"Wrote {len(content)} bytes" in result


class TestDiffWriterRead:
    """Tests for DiffWriter.read()."""

    def test_read_existing_file(self):
        """Read returns file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter()
            test_file = os.path.join(tmpdir, "test.py")
            Path(test_file).write_text("file content")

            result = writer.read(test_file)

            assert result == "file content"

    def test_read_nonexistent_file(self):
        """Read returns error for non-existent file."""
        writer = DiffWriter()

        result = writer.read("/nonexistent/path/file.py")

        assert "Error" in result
        assert "not found" in result


class TestDiffWriterDiff:
    """Tests for DiffWriter.diff()."""

    def test_diff_no_changes(self):
        """Diff returns 'no changes' when content is same."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=True)
            test_file = os.path.join(tmpdir, "test.py")
            content = "same content"
            Path(test_file).write_text(content)

            result = writer.diff(test_file, content)

            assert "No changes" in result

    def test_diff_new_file(self):
        """Diff returns empty string for new file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=True)
            test_file = os.path.join(tmpdir, "new.py")

            result = writer.diff(test_file, "new content")

            # New file has no diff (empty string triggers new file display)
            assert "No changes" in result or result == ""

    def test_diff_shows_changes(self):
        """Diff returns unified diff format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=True)
            test_file = os.path.join(tmpdir, "test.py")
            Path(test_file).write_text("line1\nline2\n")

            # Mock console to capture output
            writer._console = MagicMock()

            result = writer.diff(test_file, "line1\nline2\nline3\n")

            # Should contain diff markers
            assert "---" in result or "+line3" in result


class TestDiffWriterGenerateDiff:
    """Tests for DiffWriter._generate_diff()."""

    def test_generate_diff_addition(self):
        """Generate diff shows additions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter()
            test_file = os.path.join(tmpdir, "test.py")
            Path(test_file).write_text("line1\n")

            diff = writer._generate_diff(test_file, "line1\nline2\n")

            assert "+line2" in diff

    def test_generate_diff_deletion(self):
        """Generate diff shows deletions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter()
            test_file = os.path.join(tmpdir, "test.py")
            Path(test_file).write_text("line1\nline2\n")

            diff = writer._generate_diff(test_file, "line1\n")

            assert "-line2" in diff

    def test_generate_diff_modification(self):
        """Generate diff shows modifications."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter()
            test_file = os.path.join(tmpdir, "test.py")
            Path(test_file).write_text("old line\n")

            diff = writer._generate_diff(test_file, "new line\n")

            assert "-old line" in diff
            assert "+new line" in diff

    def test_generate_diff_new_file_returns_empty(self):
        """Generate diff returns empty string for new file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter()
            test_file = os.path.join(tmpdir, "nonexistent.py")

            diff = writer._generate_diff(test_file, "content")

            assert diff == ""


class TestDiffWriterApproval:
    """Tests for DiffWriter approval flow (mocked)."""

    def test_approval_approve(self):
        """User approves change."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=False)
            test_file = os.path.join(tmpdir, "test.py")

            with patch.object(writer, '_ask_approval', return_value='approve'):
                result = writer.write(test_file, "content")

            assert Path(test_file).exists()
            assert "Wrote" in result

    def test_approval_approve_all(self):
        """User approves all future changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=False)
            test_file = os.path.join(tmpdir, "test.py")

            with patch.object(writer, '_ask_approval', return_value='approve_all'):
                result = writer.write(test_file, "content")

            assert writer.auto_approve is True
            assert Path(test_file).exists()

    def test_approval_reject_with_feedback(self):
        """User rejects with feedback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=False)
            test_file = os.path.join(tmpdir, "test.py")

            with patch.object(writer, '_ask_approval', return_value='reject'):
                with patch('builtins.input', return_value='use snake_case'):
                    result = writer.write(test_file, "content")

            assert not Path(test_file).exists()
            assert "rejected" in result
            assert "snake_case" in result


class TestDiffWriterEncoding:
    """Tests for file encoding."""

    def test_write_utf8_content(self):
        """Write handles UTF-8 content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter(auto_approve=True)
            test_file = os.path.join(tmpdir, "test.py")
            content = "# 你好世界\nprint('こんにちは')"

            result = writer.write(test_file, content)

            assert Path(test_file).read_text(encoding='utf-8') == content

    def test_read_utf8_content(self):
        """Read handles UTF-8 content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DiffWriter()
            test_file = os.path.join(tmpdir, "test.py")
            content = "# émojis: 🎉🚀"
            Path(test_file).write_text(content, encoding='utf-8')

            result = writer.read(test_file)

            assert result == content
