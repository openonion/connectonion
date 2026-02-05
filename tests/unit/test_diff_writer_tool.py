"""Unit tests for connectonion/useful_tools/diff_writer.py

Tests cover:
- DiffWriter.write: writing files with diff display
- DiffWriter.diff: preview diff without writing
- DiffWriter.read: reading file contents
- _generate_diff: diff generation helper
- Mode-based permissions (normal, auto, plan)
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from connectonion.useful_tools.diff_writer import DiffWriter, MODE_NORMAL, MODE_AUTO, MODE_PLAN


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

            diff_text = writer.diff(f.name, "line1\nmodified\nline3\n")

            assert "-line2" in diff_text
            assert "+modified" in diff_text

    def test_diff_no_changes(self):
        """Test diff when content is identical."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("same content\n")
            f.flush()

            writer = DiffWriter()

            result = writer.diff(f.name, "same content\n")

            assert "No changes" in result

    def test_diff_new_file(self):
        """Test diff for a new file."""
        writer = DiffWriter()

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

    def test_write_with_auto_mode(self):
        """Test writing file with mode=auto."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(mode=MODE_AUTO)
            result = writer.write(str(path), "Hello, World!")

            assert path.exists()
            assert path.read_text() == "Hello, World!"
            assert "Wrote" in result
            assert "bytes" in result

    def test_write_creates_parent_directories(self):
        """Test that write creates parent directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "dir" / "file.txt"

            writer = DiffWriter(mode=MODE_AUTO)
            writer.write(str(path), "content")

            assert path.exists()
            assert path.read_text() == "content"

    def test_write_approval_flow_approve(self):
        """Test write with approval flow (user approves)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(mode=MODE_NORMAL)
            # Mock _ask_approval to return "approve"
            writer._ask_approval = Mock(return_value="approve")

            result = writer.write(str(path), "approved content")

            assert path.exists()
            assert "Wrote" in result

    def test_write_approval_flow_approve_all(self):
        """Test write with approval flow (user selects approve all)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(mode=MODE_NORMAL)
            writer._ask_approval = Mock(return_value="approve_all")

            writer.write(str(path), "content")

            # After approve_all, mode should be auto
            assert writer.mode == MODE_AUTO

    def test_write_approval_flow_reject(self):
        """Test write with approval flow (user rejects)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(mode=MODE_NORMAL)
            writer._ask_approval = Mock(return_value="reject")
            writer._ask_feedback = Mock(return_value="Please use different naming")

            result = writer.write(str(path), "rejected content")

            assert not path.exists()
            assert "rejected" in result
            assert "different naming" in result

    def test_write_plan_mode_no_write(self):
        """Test plan mode doesn't write file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(mode=MODE_PLAN)
            result = writer.write(str(path), "content")

            assert not path.exists()
            assert "[Plan mode]" in result
            assert "Would write" in result


class TestDiffWriterModes:
    """Tests for permission modes."""

    def test_default_mode_is_normal(self):
        """Test default mode is normal."""
        writer = DiffWriter()
        assert writer.mode == MODE_NORMAL

    def test_auto_mode_no_io_fallback(self):
        """Test auto mode writes without io channel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(mode=MODE_AUTO)
            writer.io = None  # No io channel

            result = writer.write(str(path), "content")

            assert path.exists()
            assert "[auto mode]" in result

    def test_normal_mode_no_io_falls_back_to_approve(self):
        """Test normal mode without io channel auto-approves."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(mode=MODE_NORMAL)
            writer.io = None  # No io channel

            result = writer.write(str(path), "content")

            # Should auto-approve since no io channel
            assert path.exists()


class TestDiffWriterIntegration:
    """Integration tests for DiffWriter."""

    def test_diff_writer_can_be_used_as_agent_tool(self):
        """Test that DiffWriter can be registered with agent."""
        from connectonion import Agent
        from connectonion.core.llm import LLMResponse
        from connectonion.core.usage import TokenUsage

        mock_llm = Mock()
        mock_llm.model = "test-model"
        mock_llm.complete.return_value = LLMResponse(
            content="Test",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        writer = DiffWriter(mode=MODE_AUTO)
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
            path = Path(tmpdir) / "test.txt"

            writer = DiffWriter(mode=MODE_AUTO)
            writer.write(str(path), "Hello, World!")

            content = writer.read(str(path))

            assert content == "Hello, World!"


class TestDiffWriterTruncation:
    """Tests for preview truncation."""

    def test_truncate_long_preview(self):
        """Test that long previews get truncated."""
        writer = DiffWriter(preview_limit=100)

        long_preview = "x" * 200
        truncated, was_truncated = writer._truncate_preview(long_preview)

        assert was_truncated
        assert len(truncated) <= 120  # 100 + "...(truncated)"
        assert "truncated" in truncated

    def test_short_preview_not_truncated(self):
        """Test that short previews are not truncated."""
        writer = DiffWriter(preview_limit=100)

        short_preview = "x" * 50
        result, was_truncated = writer._truncate_preview(short_preview)

        assert not was_truncated
        assert result == short_preview
