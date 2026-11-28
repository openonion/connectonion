"""A grep result has to name the file it came from, and a line shared by two
matches has to appear once. `grep(path=<one file>)` printed "." because the file
was its own base for relative_to(), and overlapping context blocks repeated the
shared lines, so the output read as if the line matched twice."""

import importlib
from pathlib import Path

grep_module = importlib.import_module("connectonion.useful_tools.file_tools.grep")
grep = grep_module.grep


def test_a_named_file_is_reported_by_its_name(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("alpha\nbeta alpha\n", encoding="utf-8")

    assert grep("alpha", path=str(target)).strip() == str(target)
    assert f"\n{target}:" in grep("alpha", path=str(target), output_mode="content")


def test_a_relative_named_file_keeps_the_path_it_was_given(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("alpha\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert grep("alpha", path="src/app.py").strip() == str(Path("src") / "app.py")


def test_context_shared_by_two_matches_is_printed_once(tmp_path):
    (tmp_path / "code.py").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    out = grep("two|three", path=str(tmp_path), output_mode="content", context_lines=1)

    assert out.count("2: two") == 1
    assert out.count("3: three") == 1
    assert "  > 2: two" in out
    assert "  > 3: three" in out
    assert "4: four" in out


def test_windows_that_do_not_touch_stay_separate_blocks(tmp_path):
    (tmp_path / "code.py").write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    out = grep("one|five", path=str(tmp_path), output_mode="content", context_lines=1)

    assert "  > 1: one" in out
    assert "  > 5: five" in out
    assert "\n\n" in out
