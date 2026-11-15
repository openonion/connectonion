"""Untrusted session folders must not prevent REM from preparing its next task (#3066)."""

from pathlib import Path

import pytest

from connectonion.rem import investigate, map as rem_map, project_material, project_pages, scan, sessions


@pytest.fixture(params=["exists", "stat"])
def protected(tmp_path, monkeypatch, request):
    folder = tmp_path / "protected"
    folder.mkdir()
    probe = getattr(Path, request.param)
    probes = []

    def denied(path, *args, **kwargs):
        if path == folder / ".git":
            probes.append(path)
            raise PermissionError(13, "Permission denied", str(path))
        return probe(path, *args, **kwargs)

    monkeypatch.setattr(Path, request.param, denied)
    return folder, probes


@pytest.mark.parametrize("site", ["session", "map", "workspace", "workspace-child", "worktree",
                                  "beside", "beside-child", "project", "current-line", "code", "checkout",
                                  "owner-marker", "owner-path"])
def test_each_repository_probe_treats_permission_denied_as_no_repository(protected, site):
    folder, probes = protected
    page = f"# Fern\n\n## Paths\n- {folder}\n"
    if site == "session":
        assert sessions._project_path(str(folder / ".worktrees/probe")) == str(folder / ".worktrees/probe")
    elif site == "map":
        assert rem_map._repository_folder(str(folder)) == ""
    elif site == "workspace":
        scan.project_exclusion(folder)
    elif site == "workspace-child":
        (folder.parent / "AGENTS.md").write_text("Workspace")
        scan.project_exclusion(folder.parent)
    elif site == "worktree":
        assert scan.main_checkout(str(folder)) == ""
    elif site == "beside":
        assert scan._beside(str(folder), "fern-fix") == ""
    elif site == "beside-child":
        assert scan._beside(str(folder.parent), "protected-fix") == ""
    elif site == "project":
        assert scan.not_a_project({"path": str(folder), "sessions": 1, "turns": 1}) == scan.SHORT_SESSION
    elif site == "current-line":
        assert project_pages.current_line(page) is None
    elif site == "code":
        assert project_pages._code_matches(str(folder), "fictional/fern", []) is False
    elif site == "checkout":
        assert investigate.checkout_state(str(folder)) == ""
    elif site == "owner-marker":
        assert project_material._Owners({}, None)._marker(folder) == ""
    elif site == "owner-path":
        assert project_material._Owners({}, None)(str(folder), str(folder.parent)) is None
    assert probes, f"{site} did not exercise the denied .git probe"


def test_worktree_owner_skips_unreadable_main_repository(protected, monkeypatch):
    folder, probes = protected
    worktree = folder.parent / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {folder}/.git/worktrees/probe\n")
    owners = project_material._Owners({}, None)
    monkeypatch.setattr(owners, "_usable", lambda path: True)
    assert owners.worktree(str(worktree)) is None
    assert probes


@pytest.mark.parametrize("marker", ["directory", "file", "absent"])
def test_repository_probe_preserves_git_directories_and_worktree_files(tmp_path, marker):
    git = tmp_path / ".git"
    if marker == "directory":
        git.mkdir()
    elif marker == "file":
        git.write_text("gitdir: /work/fern/.git/worktrees/probe\n")
    assert scan.is_repository(tmp_path) is (marker != "absent")


def test_repository_probe_does_not_hide_other_io_errors(tmp_path, monkeypatch):
    def broken(path):
        raise OSError(5, "Input/output error", str(path))
    monkeypatch.setattr(Path, "exists", broken)
    with pytest.raises(OSError, match="Input/output error"):
        scan.is_repository(tmp_path)
