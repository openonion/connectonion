"""Tests for file tools (read/edit/multi_edit/glob/grep/write/diff)."""
"""
LLM-Note: Tests for file tools

What it tests:
- File Tools functionality (read, edit, multi_edit, glob, grep, write)
- DiffWriter with approval flow

Components under test:
- Module: useful_tools.file_tools
- Module: useful_tools.diff_writer
"""

from types import SimpleNamespace

from connectonion.useful_tools.file_tools import read_file, edit, multi_edit, glob, grep, write
from connectonion.useful_tools.diff_writer import DiffWriter, MODE_AUTO, MODE_PLAN


class FakeIO:
    def __init__(self, responses=None):
        self.sent = []
        self._responses = list(responses or [])

    def send(self, event):
        self.sent.append(event)

    def receive(self):
        if self._responses:
            return self._responses.pop(0)
        return {}


def test_read_edit_multi_edit(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    out = read_file(str(path), offset=2, limit=1)
    assert "2\tbeta" in out

    msg = edit(str(path), "beta", "BETA")
    assert "Successfully" in msg
    assert "BETA" in path.read_text(encoding="utf-8")

    msg = multi_edit(
        str(path),
        [
            {"old_string": "alpha", "new_string": "ALPHA"},
            {"old_string": "gamma", "new_string": "GAMMA"},
        ],
    )
    assert "Successfully" in msg
    content = path.read_text(encoding="utf-8")
    assert "ALPHA" in content and "GAMMA" in content


def test_glob_and_grep(tmp_path):
    (tmp_path / "a.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("hello world\n", encoding="utf-8")

    out = glob("**/*.py", path=str(tmp_path))
    assert "a.py" in out

    out = grep("hello", path=str(tmp_path), output_mode="files")
    assert "b.txt" in out or "a.py" in out  # Both files contain 'hello'

    out = grep("hello", path=str(tmp_path), output_mode="count")
    assert "match" in out.lower()

    out = grep("(", path=str(tmp_path))
    assert "Invalid" in out or "error" in out.lower()


def test_write_new_file(tmp_path):
    """Test write function creates new files."""
    path = tmp_path / "new_file.txt"
    msg = write(str(path), "hello world")
    assert "Successfully" in msg or "wrote" in msg.lower()
    assert path.read_text(encoding="utf-8") == "hello world"


def test_write_existing_file_errors(tmp_path):
    """Test write function errors on existing files (should use edit instead)."""
    path = tmp_path / "existing.txt"
    path.write_text("original", encoding="utf-8")
    msg = write(str(path), "new content")
    assert "exists" in msg.lower() or "error" in msg.lower()
    # File should be unchanged
    assert path.read_text(encoding="utf-8") == "original"


def test_diff_writer_rejects_with_feedback(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("old", encoding="utf-8")

    io = FakeIO([
        {"answer": "No, reject and give feedback"},
        {"answer": "Please do something else"},
    ])
    agent = SimpleNamespace(io=io)

    writer = DiffWriter(mode=MODE_AUTO)
    # force normal mode for approval
    writer.mode = "normal"
    msg = writer.write(agent, str(path), "new")
    assert "User rejected" in msg
    # File should remain unchanged
    assert path.read_text(encoding="utf-8") == "old"
    assert any(e.get("type") == "diff_preview" for e in io.sent)


def test_diff_writer_plan_mode(tmp_path):
    path = tmp_path / "file.txt"
    writer = DiffWriter(mode=MODE_PLAN)
    msg = writer.write(SimpleNamespace(io=None), str(path), "content")
    assert msg.startswith("[Plan mode]")
    assert not path.exists()
