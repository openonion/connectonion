"""Tests for useful_tools file helpers (read/write/edit/glob/grep)."""
"""
LLM-Note: Tests for useful tools files

What it tests:
- Useful Tools Files functionality

Components under test:
- Module: useful_tools_files
"""


from types import SimpleNamespace

from connectonion.useful_tools.file_tools import (
    read_file,
    edit,
    multi_edit,
    write,
    glob as glob_files,
    grep as grep_files,
    FileTools,
)


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


def test_write_simple_function(tmp_path):
    """Test simplified write() function from write.py."""
    path = tmp_path / "out.txt"

    # Create new file
    msg = write(str(path), "hello")
    assert "Successfully wrote" in msg
    assert path.read_text(encoding="utf-8") == "hello"

    # Try to overwrite existing file - should fail
    msg = write(str(path), "world")
    assert "Error:" in msg
    assert "already exists" in msg
    assert "edit()" in msg
    assert path.read_text(encoding="utf-8") == "hello"  # File unchanged

    # Create nested directories
    nested = tmp_path / "sub" / "dir" / "file.txt"
    msg = write(str(nested), "nested content")
    assert "Successfully wrote" in msg
    assert nested.read_text(encoding="utf-8") == "nested content"


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


def test_file_tools_read_before_edit_validation(tmp_path):
    """Test FileTools enforces read-before-edit and tracks snapshots."""
    path = tmp_path / "test.txt"
    path.write_text("original content\n", encoding="utf-8")

    ft = FileTools()

    # Edit without reading first should fail
    msg = ft.edit(str(path), "original", "new")
    assert "Read" in msg and "before editing" in msg

    # Read the file (snapshot tracked)
    content = ft.read_file(str(path))
    assert "original content" in content

    # Now edit should succeed
    msg = ft.edit(str(path), "original", "modified")
    assert "Successfully" in msg
    assert path.read_text(encoding="utf-8") == "modified content\n"

    # Sequential edits should work (snapshot auto-updated)
    msg = ft.edit(str(path), "modified", "updated")
    assert "Successfully" in msg
    assert path.read_text(encoding="utf-8") == "updated content\n"


def test_file_tools_stale_read_detection(tmp_path):
    """Test FileTools detects external file changes (stale read)."""
    path = tmp_path / "test.txt"
    path.write_text("version 1\n", encoding="utf-8")

    ft = FileTools()

    # Read and edit
    ft.read_file(str(path))
    msg = ft.edit(str(path), "version 1", "version 2")
    assert "Successfully" in msg

    # External change (simulating another process)
    path.write_text("version 3\n", encoding="utf-8")

    # Edit should detect stale read
    msg = ft.edit(str(path), "version 2", "version 4")
    assert "changed since last read" in msg

    # Re-read and edit should work
    ft.read_file(str(path))
    msg = ft.edit(str(path), "version 3", "version 4")
    assert "Successfully" in msg


def test_file_tools_multi_edit_validation(tmp_path):
    """Test multi_edit also enforces read-before-edit."""
    path = tmp_path / "multi.txt"
    path.write_text("foo\nbar\nbaz\n", encoding="utf-8")

    ft = FileTools()

    # multi_edit without reading first
    msg = ft.multi_edit(
        str(path),
        [
            {"old_string": "foo", "new_string": "FOO"},
        ],
    )
    assert "Read" in msg and "before editing" in msg

    # After reading
    ft.read_file(str(path))
    msg = ft.multi_edit(
        str(path),
        [
            {"old_string": "foo", "new_string": "FOO"},
            {"old_string": "bar", "new_string": "BAR"},
        ],
    )
    assert "Successfully" in msg
    assert path.read_text(encoding="utf-8") == "FOO\nBAR\nbaz\n"


def test_file_tools_write_no_snapshot_check(tmp_path):
    """Test write() doesn't require prior read (full overwrite)."""
    path = tmp_path / "write.txt"

    ft = FileTools()

    # write() should work without prior read
    msg = ft.write(str(path), "new file content")
    assert "Successfully wrote" in msg
    assert path.read_text(encoding="utf-8") == "new file content"

    # Snapshot should be tracked after write (for subsequent edits)
    msg = ft.edit(str(path), "new file", "updated")
    assert "Successfully" in msg


def test_file_tools_permission_read_only(tmp_path):
    """Test read-only permission blocks write operations."""
    path = tmp_path / "readonly.txt"
    path.write_text("content\n", encoding="utf-8")

    ft = FileTools(permission="read")

    # Read operations should work
    content = ft.read_file(str(path))
    assert "content" in content

    globbed = ft.glob("*.txt", path=str(tmp_path))
    assert "readonly.txt" in globbed

    grepped = ft.grep("content", path=str(tmp_path))
    assert "readonly.txt" in grepped

    # Write operations should fail
    msg = ft.edit(str(path), "content", "new")
    assert "Permission denied" in msg

    msg = ft.multi_edit(str(path), [{"old_string": "content", "new_string": "new"}])
    assert "Permission denied" in msg

    msg = ft.write(str(path), "new content")
    assert "Permission denied" in msg


# ============================================================================
# Additional comprehensive tests for all file operations
# ============================================================================

def test_read_file_long_lines(tmp_path):
    """Test read_file truncates very long lines."""
    path = tmp_path / "long.txt"
    long_line = "x" * 600  # Over 500 char limit
    path.write_text(f"{long_line}\nshort\n", encoding="utf-8")

    out = read_file(str(path))
    assert "..." in out  # Truncated
    assert "short" in out


def test_edit_unique_string_requirement(tmp_path):
    """Test edit() requires unique strings."""
    path = tmp_path / "dup.txt"
    path.write_text("foo\nfoo\nbar\n", encoding="utf-8")

    # Should fail without replace_all
    msg = edit(str(path), "foo", "FOO")
    assert "appears 2 times" in msg
    assert "replace_all" in msg

    # Should work with replace_all
    msg = edit(str(path), "foo", "FOO", replace_all=True)
    assert "Replaced 2 occurrences" in msg
    assert path.read_text(encoding="utf-8") == "FOO\nFOO\nbar\n"


def test_multi_edit_empty_list(tmp_path):
    """Test multi_edit handles empty edit list."""
    path = tmp_path / "test.txt"
    path.write_text("content\n", encoding="utf-8")

    msg = multi_edit(str(path), [])
    assert "Error: No edits provided" in msg


def test_multi_edit_missing_fields(tmp_path):
    """Test multi_edit validates edit structure."""
    path = tmp_path / "test.txt"
    path.write_text("content\n", encoding="utf-8")

    msg = multi_edit(str(path), [{"new_string": "new"}])
    assert "missing 'old_string'" in msg


def test_write_creates_parent_dirs(tmp_path):
    """Test write() creates parent directories automatically."""
    path = tmp_path / "a" / "b" / "c" / "file.txt"

    msg = write(str(path), "content")
    assert "Successfully wrote" in msg
    assert path.read_text(encoding="utf-8") == "content"


def test_glob_patterns(tmp_path):
    """Test various glob patterns."""
    (tmp_path / "test.py").write_text("", encoding="utf-8")
    (tmp_path / "test.js").write_text("", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.py").write_text("", encoding="utf-8")

    # All Python files
    out = glob_files("**/*.py", path=str(tmp_path))
    assert "test.py" in out
    assert "nested.py" in out
    assert "test.js" not in out

    # Top-level only
    out = glob_files("*.py", path=str(tmp_path))
    assert "test.py" in out
    assert "nested.py" not in out


def test_glob_max_results(tmp_path):
    """Test glob returns max 100 results."""
    # Create 150 files
    for i in range(150):
        (tmp_path / f"file{i}.txt").write_text("", encoding="utf-8")

    out = glob_files("*.txt", path=str(tmp_path))
    assert "and 50 more files" in out


def test_grep_with_context(tmp_path):
    """Test grep shows context lines."""
    path = tmp_path / "code.py"
    path.write_text("line1\nline2\nMATCH\nline4\nline5\n", encoding="utf-8")

    out = grep_files("MATCH", path=str(tmp_path), output_mode="content", context_lines=1)
    assert "line2" in out  # Before
    assert "MATCH" in out
    assert "line4" in out  # After


def test_grep_ignore_case(tmp_path):
    """Test grep case sensitivity."""
    path = tmp_path / "text.txt"
    path.write_text("Hello World\n", encoding="utf-8")

    # Case sensitive (default)
    out = grep_files("hello", path=str(tmp_path), output_mode="files")
    assert "No matches" in out

    # Case insensitive
    out = grep_files("hello", path=str(tmp_path), output_mode="files", ignore_case=True)
    assert "text.txt" in out


def test_grep_file_pattern_filter(tmp_path):
    """Test grep filters by file pattern."""
    (tmp_path / "test.py").write_text("import sys\n", encoding="utf-8")
    (tmp_path / "test.txt").write_text("import nothing\n", encoding="utf-8")

    out = grep_files("import", path=str(tmp_path), file_pattern="*.py", output_mode="files")
    assert "test.py" in out
    assert "test.txt" not in out


def test_file_tools_glob_and_grep(tmp_path):
    """Test FileTools.glob() and grep() work correctly."""
    (tmp_path / "a.py").write_text("code\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text("text\n", encoding="utf-8")

    ft = FileTools()

    # Glob
    files = ft.glob("*.py", path=str(tmp_path))
    assert "a.py" in files

    # Grep
    matches = ft.grep("code", path=str(tmp_path))
    assert "a.py" in matches


def test_file_tools_read_offset_limit(tmp_path):
    """Test FileTools.read_file() with offset and limit."""
    path = tmp_path / "lines.txt"
    path.write_text("1\n2\n3\n4\n5\n", encoding="utf-8")

    ft = FileTools()

    # Read middle section
    content = ft.read_file(str(path), offset=2, limit=2)
    assert "2\t2" in content
    assert "3\t3" in content
    assert "1\t1" not in content
    assert "4\t4" not in content


def test_file_tools_write_prevents_overwrite(tmp_path):
    """Test FileTools.write() prevents overwriting existing files."""
    path = tmp_path / "existing.txt"
    path.write_text("original\n", encoding="utf-8")

    ft = FileTools()

    msg = ft.write(str(path), "new content")
    assert "Error:" in msg
    assert "already exists" in msg
    assert path.read_text(encoding="utf-8") == "original\n"


def test_file_tools_edit_file_not_found(tmp_path):
    """Test FileTools.edit() handles missing files after read."""
    path = tmp_path / "temp.txt"
    path.write_text("content\n", encoding="utf-8")

    ft = FileTools()
    ft.read_file(str(path))

    # Delete file externally
    path.unlink()

    msg = ft.edit(str(path), "content", "new")
    assert "Error:" in msg
    assert "no longer exists" in msg


def test_standalone_functions_no_validation(tmp_path):
    """Test standalone functions work without FileTools validation."""
    path = tmp_path / "standalone.txt"
    path.write_text("original\n", encoding="utf-8")

    # edit() works without prior read (no FileTools wrapper)
    msg = edit(str(path), "original", "modified")
    assert "Successfully" in msg
    assert path.read_text(encoding="utf-8") == "modified\n"


def test_all_operations_integration(tmp_path):
    """Integration test using all operations together."""
    ft = FileTools()

    # Create file
    file1 = tmp_path / "app.py"
    msg = ft.write(str(file1), "def hello():\n    pass\n")
    assert "Successfully wrote" in msg

    # Read and edit
    content = ft.read_file(str(file1))
    assert "hello" in content

    msg = ft.edit(str(file1), "hello", "goodbye")
    assert "Successfully" in msg

    # Multi-edit
    msg = ft.multi_edit(str(file1), [
        {"old_string": "goodbye", "new_string": "greet"},
        {"old_string": "pass", "new_string": "print('hi')"}
    ])
    assert "Successfully" in msg

    # Verify final content
    final = file1.read_text(encoding="utf-8")
    assert "greet" in final
    assert "print('hi')" in final

    # Search
    matches = ft.grep("greet", path=str(tmp_path))
    assert "app.py" in matches

    files = ft.glob("*.py", path=str(tmp_path))
    assert "app.py" in files
