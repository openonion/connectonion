"""Tests for co_ai file tools (read/edit/multi_edit/glob/grep/write/diff)."""

from types import SimpleNamespace

from connectonion.cli.co_ai.tools.read import read_file
from connectonion.cli.co_ai.tools.edit import edit
from connectonion.cli.co_ai.tools.multi_edit import multi_edit
from connectonion.cli.co_ai.tools.glob import glob as glob_files
from connectonion.cli.co_ai.tools.grep import grep as grep_files
from connectonion.cli.co_ai.tools.write import write, Write
from connectonion.cli.co_ai.tools.diff_writer import DiffWriter, MODE_AUTO, MODE_PLAN


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

    out = glob_files("**/*.py", path=str(tmp_path))
    assert "a.py" in out

    out = grep_files("hello", path=str(tmp_path), output_mode="files")
    assert "b.txt" in out

    out = grep_files("hello", path=str(tmp_path), output_mode="count")
    assert "matches" in out

    out = grep_files("(", path=str(tmp_path))
    assert "Invalid regex" in out


def test_write_wrapper_and_write_class(tmp_path, monkeypatch):
    import connectonion.cli.co_ai.tools.write as write_mod
    monkeypatch.setattr(write_mod, "_writer", None)

    agent = SimpleNamespace(io=None)
    path = tmp_path / "out.txt"
    msg = write(agent, str(path), "hello")
    assert "Wrote" in msg
    assert path.read_text(encoding="utf-8") == "hello"

    writer = Write(mode="plan")
    plan_path = tmp_path / "plan.txt"
    msg = writer.write(agent, str(plan_path), "content")
    assert msg.startswith("[Plan mode]")
    assert not plan_path.exists()

    assert writer.read(str(path)) == "hello"


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
