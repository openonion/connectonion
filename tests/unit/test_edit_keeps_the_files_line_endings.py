"""`edit` rewrote every line ending in the file it touched.

`Path.read_text` normalises CRLF to LF and `Path.write_text` translates LF to
`os.linesep`. Editing one line of a CRLF file therefore rewrote the whole file
to LF on Linux, and editing one line of an LF file rewrote the whole file to
CRLF on Windows: a one-line change became a whole-file diff. The tool now works
on the bytes as they are and writes back in the file's own style.
"""

from connectonion.core.tool_result import ToolFailure
from connectonion.useful_tools.file_tools.edit import edit


def test_crlf_file_keeps_crlf(tmp_path):
    path = tmp_path / "crlf.txt"
    path.write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")

    assert "Successfully edited" in edit(str(path), "beta", "delta")

    assert path.read_bytes() == b"alpha\r\ndelta\r\ngamma\r\n"


def test_lf_file_keeps_lf(tmp_path):
    path = tmp_path / "lf.txt"
    path.write_bytes(b"alpha\nbeta\ngamma\n")

    assert "Successfully edited" in edit(str(path), "beta", "delta")

    assert path.read_bytes() == b"alpha\ndelta\ngamma\n"


def test_multi_line_old_string_written_with_lf_still_matches_a_crlf_file(tmp_path):
    path = tmp_path / "crlf.txt"
    path.write_bytes(b"one\r\ntwo\r\nthree\r\n")

    result = edit(str(path), "one\ntwo", "uno\ndos")

    assert "Successfully edited" in result
    assert path.read_bytes() == b"uno\r\ndos\r\nthree\r\n"


def test_multi_line_new_string_adopts_the_files_endings(tmp_path):
    path = tmp_path / "crlf.txt"
    path.write_bytes(b"one\r\ntwo\r\n")

    edit(str(path), "one", "first\nsecond")

    assert path.read_bytes() == b"first\r\nsecond\r\ntwo\r\n"


def test_replace_all_keeps_endings(tmp_path):
    path = tmp_path / "crlf.txt"
    path.write_bytes(b"x\r\ny\r\nx\r\n")

    assert "Replaced 2 occurrences" in edit(str(path), "x", "z", replace_all=True)

    assert path.read_bytes() == b"z\r\ny\r\nz\r\n"


def test_byte_order_mark_survives(tmp_path):
    path = tmp_path / "bom.txt"
    path.write_bytes(b"\xef\xbb\xbfalpha\r\nbeta\r\n")

    edit(str(path), "beta", "gamma")

    assert path.read_bytes() == b"\xef\xbb\xbfalpha\r\ngamma\r\n"


def test_a_file_that_is_not_utf8_is_reported_and_left_alone(tmp_path):
    path = tmp_path / "gbk.txt"
    original = "你好".encode("gbk")
    path.write_bytes(original)

    result = edit(str(path), "a", "b")

    assert isinstance(result, ToolFailure)
    assert "not UTF-8" in result
    assert path.read_bytes() == original


def test_a_missing_string_reports_the_file_unchanged(tmp_path):
    path = tmp_path / "crlf.txt"
    path.write_bytes(b"alpha\r\nbeta\r\n")

    result = edit(str(path), "missing", "x")

    assert "String not found" in result
    assert path.read_bytes() == b"alpha\r\nbeta\r\n"
