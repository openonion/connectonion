"""Unit tests for connectonion/useful_tools/diff_writer.py

Tests cover:
- DiffWriter.write: writing files with diff display
- DiffWriter.diff: preview diff without writing
- DiffWriter.read: reading file contents
- _generate_diff: diff generation helper
- auto_approve mode
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from connectonion.useful_tools.diff_writer import DiffWriter


class TestDiffWriterRead:
    """Tests for DiffWriter.read method."""

    def test_read_existing_file(self):
        """Test reading an existing file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Hello, World!")
            f.flush()

            writer = DiffWriter()
            content = writer.read(f.name)

            assert content == "Hello, World!"

    def test_read_nonexistent_file(self):
        """Test reading a file that doesn't exist."""
        writer = DiffWriter()
        result = writer.read("/nonexistent/path/file.txt")

        assert "Error" in result
        assert "not found" in result


class TestDiffWriterDiff:
    """Tests for DiffWriter.diff method."""

    def test_diff_shows_changes(self):
        """Test that diff shows changes between old and new content."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()

            writer = DiffWriter()
            # Mock console to avoid output
            writer._console = Mock()

            diff_text = writer.diff(f.name, "line1\nmodified\nline3\n")

            assert "-line2" in diff_text
            assert "+modified" in diff_text

    def test_diff_no_changes(self):
        """Test diff when content is identical."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("same content\n")
            f.flush()

            writer = DiffWriter()
            writer._console = Mock()

            result = writer.diff(f.name, "same content\n")

            assert "No changes" in result

    def test_diff_new_file(self):
        """Test diff for a new file."""
        writer = DiffWriter()
        writer._console = Mock()

        result = writer.diff("/tmp/nonexistent_test_file.txt", "new content")

        assert "No changes" in result


class TestDiffWriterGenerateDiff:
    """Tests for DiffWriter._generate_diff method."""

    def test_generate_diff_existing_file(self):
        """Test diff generation for existing file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("original\n")
            f.flush()

            writer = DiffWriter()
            diff = writer._generate_diff(f.name, "modified\n")

            assert "-original" in diff
            assert "+modified" in diff

    def test_generate_diff_new_file(self):
        """Test diff generation for new file (returns empty string)."""
        writer = DiffWriter()
        diff = writer._generate_diff("/nonexistent/file.txt", "new content")

        assert diff == ""


class TestDiffWriterWrite:
    """Tests for DiffWriter.write method."""

    def test_write_with_auto_approve(self):
        """Test writing file with auto_approve=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(auto_approve=True)
            result = writer.write(str(path), "Hello, World!")

            assert path.exists()
            assert path.read_text() == "Hello, World!"
            assert "Wrote" in result
            assert "bytes" in result

    def test_write_creates_parent_directories(self):
        """Test that write creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "dir" / "file.txt"

            writer = DiffWriter(auto_approve=True)
            writer.write(str(path), "content")

            assert path.exists()
            assert path.read_text() == "content"

    def test_write_approval_flow_approve(self):
        """Test write with approval flow (user approves)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(auto_approve=False)
            writer._console = Mock()

            with patch.object(writer, '_ask_approval', return_value='approve'):
                result = writer.write(str(path), "approved content")

            assert path.exists()
            assert "Wrote" in result

    def test_write_approval_flow_approve_all(self):
        """Test write with approval flow (user selects approve all)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(auto_approve=False)
            writer._console = Mock()

            with patch.object(writer, '_ask_approval', return_value='approve_all'):
                writer.write(str(path), "content")

            # After approve_all, auto_approve should be True
            assert writer.auto_approve is True

    def test_write_approval_flow_reject(self):
        """Test write with approval flow (user rejects)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(auto_approve=False)
            writer._console = Mock()

            with patch.object(writer, '_ask_approval', return_value='reject'):
                with patch('builtins.input', return_value='Please use different naming'):
                    result = writer.write(str(path), "rejected content")

            assert not path.exists()
            assert "rejected" in result
            assert "different naming" in result


class TestDiffWriterDisplayMethods:
    """Tests for display helper methods."""

    def test_display_diff_colorizes_output(self):
        """Test that _display_diff creates colorized output."""
        writer = DiffWriter()
        writer._console = Mock()

        diff_text = """--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 line1
-old line
+new line
 line3
"""
        writer._display_diff(diff_text, "file.txt")

        # Verify console.print was called with a Panel
        writer._console.print.assert_called_once()

    def test_display_new_file_shows_preview(self):
        """Test that _display_new_file shows a preview."""
        writer = DiffWriter()
        writer._console = Mock()

        content = "line1\nline2\nline3"
        writer._display_new_file("new_file.txt", content)

        writer._console.print.assert_called_once()

    def test_display_new_file_truncates_long_content(self):
        """Test that long content is truncated in preview."""
        writer = DiffWriter()
        writer._console = Mock()

        # Create content with more than 50 lines
        content = "\n".join([f"line{i}" for i in range(100)])
        writer._display_new_file("long_file.txt", content)

        # Should still display (truncated internally)
        writer._console.print.assert_called_once()


class TestDiffWriterIntegration:
    """Integration tests for DiffWriter."""

    def test_diff_writer_can_be_used_as_agent_tool(self):
        """Test that DiffWriter can be registered with agent."""
        from connectonion import Agent
        from connectonion.llm import LLMResponse
        from connectonion.usage import TokenUsage

        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="Test",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        writer = DiffWriter(auto_approve=True)
        agent = Agent(
            "test",
            llm=mock_llm,
            tools=[writer],
            log=False,
        )

        # Verify writer methods are accessible
        assert agent.tools.get("write") is not None
        assert agent.tools.get("diff") is not None
        assert agent.tools.get("read") is not None

    def test_round_trip_write_and_read(self):
        """Test writing and reading back content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "roundtrip.txt")
            content = "Round trip test content\nWith multiple lines\n"

            writer = DiffWriter(auto_approve=True)
            writer.write(path, content)
            read_content = writer.read(path)

            assert read_content == content
