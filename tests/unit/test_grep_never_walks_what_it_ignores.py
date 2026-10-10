"""#1453: grep listed every file under `path` before filtering, so one call
from $HOME walked node_modules, Library and caches for 26 minutes in-process.
Ignored directories are pruned during the walk, and the walk has a ceiling."""

import importlib

# The package re-exports the function under the module's name, so reach the module itself.
grep_module = importlib.import_module("connectonion.useful_tools.file_tools.grep")
grep = grep_module.grep


def test_ignored_directories_are_never_entered(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("needle\n")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "b.js").write_text("needle\n")
    entered = []
    real_walk = grep_module.os.walk
    def walk(top, **kwargs):
        for dirpath, dirnames, filenames in real_walk(top, **kwargs):
            entered.append(dirpath)
            yield dirpath, dirnames, filenames
    monkeypatch.setattr(grep_module.os, "walk", walk)

    assert grep("needle", path=str(tmp_path)).strip() == "src/a.py"
    assert not [d for d in entered if "node_modules" in d]


def test_a_huge_tree_stops_at_the_ceiling_and_says_so(tmp_path, monkeypatch):
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_text("nothing here\n")
    monkeypatch.setattr(grep_module, "MAX_FILES", 5)

    result = grep("needle", path=str(tmp_path))

    assert "stopped after 5 files" in result


def test_file_pattern_still_filters(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("needle\n")
    (tmp_path / "pkg" / "a.md").write_text("needle\n")

    assert grep("needle", path=str(tmp_path), file_pattern="*.py").strip() == "pkg/a.py"


def test_a_directory_search_skips_huge_files_but_a_named_one_is_read(tmp_path):
    big = tmp_path / "huge.log"
    big.write_text("x" * (grep_module.MAX_FILE_BYTES + 1) + "\nneedle\n")

    assert grep("needle", path=str(tmp_path)).startswith("No matches")
    assert not grep("needle", path=str(big)).startswith("No matches")
