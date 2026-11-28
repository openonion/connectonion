"""`read_file` decoded every file as plain UTF-8.

A file saved with a byte-order mark then reached the agent as a literal
U+FEFF glued to the first line, and a UTF-16 file reached it as NUL-separated
mojibake. Neither is editable afterwards: `edit` looks for the text the agent
was shown, and the agent was shown the wrong text.
"""

import codecs

import connectonion.useful_tools.file_tools.read as read_module
from connectonion.useful_tools.file_tools.read import read_file


def _written(tmp_path, name: str, text: str, encoding: str):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return path


def test_utf8_bom_does_not_leak_into_the_first_line(tmp_path):
    path = _written(tmp_path, "bom.txt", "héllo\nwörld", "utf-8-sig")

    assert path.read_bytes().startswith(codecs.BOM_UTF8)
    output = read_file(str(path))

    assert "\ufeff" not in output
    assert output.splitlines() == ["     1\théllo", "     2\twörld"]


def test_utf16_little_endian_is_read_as_text(tmp_path):
    path = tmp_path / "le.txt"
    path.write_bytes(codecs.BOM_UTF16_LE + "héllo\nwörld".encode("utf-16-le"))

    output = read_file(str(path))

    assert output.splitlines() == ["     1\théllo", "     2\twörld"]


def test_utf16_big_endian_is_read_as_text(tmp_path):
    path = tmp_path / "be.txt"
    path.write_bytes(codecs.BOM_UTF16_BE + "hello\nworld".encode("utf-16-be"))

    output = read_file(str(path))

    assert output.splitlines() == ["     1\thello", "     2\tworld"]


def test_utf32_is_not_mistaken_for_utf16(tmp_path):
    path = tmp_path / "u32.txt"
    path.write_bytes(codecs.BOM_UTF32_LE + "hello\nworld".encode("utf-32-le"))

    output = read_file(str(path))

    assert output.splitlines() == ["     1\thello", "     2\tworld"]


def test_plain_utf8_is_unchanged(tmp_path):
    path = _written(tmp_path, "plain.txt", "héllo", "utf-8")

    output = read_file(str(path))

    assert output == "     1\théllo"


def test_undecodable_bytes_are_replaced_instead_of_raising(tmp_path):
    path = tmp_path / "gbk.txt"
    path.write_bytes("你好".encode("gbk"))

    output = read_file(str(path))

    assert "\ufffd" in output


def test_a_mark_is_only_honoured_at_the_start_of_the_file(tmp_path):
    # U+FEFF in the middle of a file is a zero-width no-break space, not a mark.
    path = _written(tmp_path, "middle.txt", "alpha\n\uFEFFbeta", "utf-8")

    output = read_file(str(path))

    assert output.splitlines() == ["     1\talpha", "     2\t\uFEFFbeta"]


def test_offset_and_limit_still_apply_to_a_bom_file(tmp_path):
    path = _written(tmp_path, "many.txt", "\n".join(f"line {i}" for i in range(1, 6)), "utf-8-sig")

    output = read_file(str(path), offset=3, limit=2)

    assert output.splitlines()[0].strip() == "3\tline 3"
    assert "line 5" not in output
