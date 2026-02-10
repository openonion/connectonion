"""Tests for useful_tools file helpers (read/write/edit/glob/grep)."""

from types import SimpleNamespace

from connectonion.useful_tools.read_file import read_file
from connectonion.useful_tools.edit import edit
from connectonion.useful_tools.multi_edit import multi_edit
from connectonion.useful_tools.write_file import write, FileWriter
from connectonion.useful_tools.glob_files import glob as glob_files
from connectonion.useful_tools.grep_files import grep as grep_files


def test_read_file_offset_limit(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text("a\nb\nc\nd\n", encoding="utf-8")

    out = read_file(str(path))
    assert "1\ta" in out
    assert "4\td" in out

    out = read_file(str(path), offset=2, limit=2)
    assert "2\tb" in out
    assert "3\tc" in out
    assert "4\td" not in out


def test_read_file_errors(tmp_path):
    missing = tmp_path / "missing.txt"
    assert "does not exist" in read_file(str(missing))

    directory = tmp_path / "dir"
    directory.mkdir()
    assert "not a file" in read_file(str(directory))


def test_edit_replaces_and_errors(tmp_path):
    path = tmp_path / "edit.txt"
    path.write_text("hello\nhello\n", encoding="utf-8")

    # Non-unique without replace_all
    msg = edit(str(path), "hello", "hi")
    assert "appears" in msg and "replace_all" in msg

    # Replace all
    msg = edit(str(path), "hello", "hi", replace_all=True)
    assert "Replaced" in msg
    assert path.read_text(encoding="utf-8") == "hi\nhi\n"

    # Not found
    msg = edit(str(path), "nope", "x")
    assert "String not found" in msg


def test_multi_edit_atomic_success_and_failure(tmp_path):
    path = tmp_path / "multi.txt"
    path.write_text("foo\nbar\nbaz\n", encoding="utf-8")

    msg = multi_edit(
        str(path),
        [
            {"old_string": "foo", "new_string": "FOO"},
            {"old_string": "bar", "new_string": "BAR"},
        ],
    )
    assert "Successfully" in msg
    assert path.read_text(encoding="utf-8") == "FOO\nBAR\nbaz\n"

    # Atomic rollback on failure
    path.write_text("one\ntwo\n", encoding="utf-8")
    msg = multi_edit(
        str(path),
        [
            {"old_string": "one", "new_string": "1"},
            {"old_string": "missing", "new_string": "x"},
        ],
    )
    assert "No changes were saved" in msg
    assert path.read_text(encoding="utf-8") == "one\ntwo\n"


def test_write_file_wrapper_and_filewriter(tmp_path, monkeypatch):
    # Reset global writer between tests
    import connectonion.useful_tools.write_file as write_mod
    monkeypatch.setattr(write_mod, "_writer", None)

    path = tmp_path / "out.txt"
    agent = SimpleNamespace(io=None)

    msg = write(agent, str(path), "hello")
    assert "Wrote" in msg
    assert path.read_text(encoding="utf-8") == "hello"

    # Plan mode should not write
    writer = FileWriter(mode="plan")
    plan_path = tmp_path / "plan.txt"
    msg = writer.write(agent, str(plan_path), "content")
    assert msg.startswith("[Plan mode]")
    assert not plan_path.exists()

    # diff/read passthrough
    diff = writer.diff(str(path), "hello")
    assert "No changes" in diff
    content = writer.read(str(path))
    assert content == "hello"


def test_glob_files_and_grep_files(tmp_path):
    (tmp_path / "a.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("hello world\n", encoding="utf-8")
    ignore_dir = tmp_path / "__pycache__"
    ignore_dir.mkdir()
    (ignore_dir / "c.py").write_text("print('no')\n", encoding="utf-8")

    out = glob_files("**/*.py", path=str(tmp_path))
    assert "a.py" in out
    assert "__pycache__" not in out

    out = grep_files("hello", path=str(tmp_path), output_mode="files")
    assert "b.txt" in out

    out = grep_files("hello", path=str(tmp_path), output_mode="count")
    assert "matches" in out

    out = grep_files("hello", path=str(tmp_path), output_mode="content")
    assert "b.txt" in out

    # Invalid regex
    out = grep_files("(", path=str(tmp_path))
    assert "Invalid regex" in out

    # Missing path
    out = glob_files("*.py", path=str(tmp_path / "missing"))
    assert "does not exist" in out
