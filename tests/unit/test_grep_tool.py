from pathlib import Path

import pytest

from connectonion.useful_tools.file_tools.grep import grep


class TestGrepPrunedWalk:
    def test_ignored_directories_are_pruned_and_not_searched(self, tmp_path):
        (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
        (tmp_path / "node_modules" / "pkg" / "hit.py").write_text("NEEDLE")
        (tmp_path / "src").mkdir(parents=True)
        (tmp_path / "src" / "hit.py").write_text("NEEDLE")
        (tmp_path / ".git").mkdir(parents=True)
        (tmp_path / ".git" / "config").write_text("NEEDLE")

        result = grep("NEEDLE", str(tmp_path))

        assert "src" in result
        assert "node_modules" not in result
        assert ".git" not in result

    def test_no_eager_materialisation_via_path_glob(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_text("hello")

        def _forbidden_glob(self, pattern):
            raise AssertionError("eager Path.glob must not be used by grep")

        monkeypatch.setattr(Path, "glob", _forbidden_glob)

        result = grep("x", str(tmp_path))

        assert isinstance(result, str)

    def test_max_files_cap_truncates_and_says_so(self, tmp_path):
        for i in range(12):
            (tmp_path / f"f{i:02d}.txt").write_text("TOKEN")

        result = grep("TOKEN", str(tmp_path), max_files=5)

        assert "max_files" in result
        assert "f11.txt" not in result

        nomatch_dir = tmp_path / "nomatch"
        nomatch_dir.mkdir()
        for i in range(3):
            (nomatch_dir / f"n{i}.txt").write_text("nothing here")

        result2 = grep("ABSENT", str(nomatch_dir), max_files=2)

        assert "No matches found" in result2
        assert "max_files" in result2

    def test_file_pattern_and_normal_search_still_work(self, tmp_path):
        nested = tmp_path / "nested"
        nested.mkdir(parents=True)
        (nested / "a.py").write_text("TOKEN")
        (nested / "a.md").write_text("TOKEN")

        filtered = grep("TOKEN", str(tmp_path), file_pattern="*.py")

        assert "a.py" in filtered
        assert "a.md" not in filtered

        unfiltered = grep("TOKEN", str(tmp_path))

        assert "a.py" in unfiltered
        assert "a.md" in unfiltered
