"""Worktree evidence files the owner's words under the project they developed."""

import os
import types
from datetime import timedelta

import pytest

from connectonion.rem import project_material
from tests.unit.test_rem_project_workspace import NOW, claude_session, codex_session


@pytest.fixture
def material(tmp_path, monkeypatch):
    home = tmp_path / "home"
    projects = home / "platform"
    for name in ("meridian", "pebble"):
        (projects / name / ".git").mkdir(parents=True)
    (projects / "atlas").mkdir()
    (projects / "CLAUDE.md").write_text("# Workspace\n")
    real = project_material.project_exclusion
    monkeypatch.setattr(project_material, "project_exclusion", lambda path:
                        "" if path.is_relative_to(home) and real(path) == "temporary execution directory"
                        else real(path))
    assert project_material.project_exclusion(projects) == project_material.CONTAINER
    sessions = tmp_path / "sessions"
    return types.SimpleNamespace(projects=projects, repo=projects / "meridian", atlas=projects / "atlas",
                                 scratch=tmp_path / "scratchpad", sessions=sessions, rem=home / "notebook",
                                 folders={str(projects / "atlas"): "projects/atlas.md"})


def worktree(material, name="fix-parser", branch="feat/parser", *, relative=False):
    folder = material.scratch / name
    folder.mkdir(parents=True)
    gitdir = material.repo / ".git/worktrees" / name
    gitdir.mkdir(parents=True)
    (gitdir / "HEAD").write_text(f"ref: refs/heads/{branch}\n")
    target = os.path.relpath(gitdir, folder) if relative else str(gitdir)
    (folder / ".git").write_text(f"gitdir: {target}\n")
    return folder


def messages(material, cwd, target, *, kind="codex"):
    path = material.sessions / "rollout-parser.jsonl"
    if kind == "codex":
        codex_session(path, str(cwd), [("Fix the parser.", 1, [("shell", {
            "file_path": str(target), "old_string": "old", "new_string": "new"})])])
    else:
        claude_session(path, [(str(cwd), "Fix the parser.", 1, [
            ("Edit", {"file_path": str(target), "old_string": "old", "new_string": "new"}, str(cwd))])])
    return project_material.session_messages(
        {"source": {"kind": kind, "root": str(material.sessions)}}, since=NOW - timedelta(days=7),
        rem_root=material.rem, folders=material.folders)


@pytest.mark.parametrize("kind", ["codex", "claude-code"])
@pytest.mark.parametrize("relative", [False, True])
def test_container_worktree_evidence_goes_to_main_repository(material, kind, relative):
    folder = worktree(material, relative=relative)
    kept, counts = messages(material, material.projects, folder / "src/x.py", kind=kind)
    assert [(m["cwd"], m["typed_in"]) for m in kept] == [(str(material.repo), str(material.projects))]
    assert counts["attributed"] == 1 and counts["excluded"] == {}


@pytest.mark.parametrize("name,branch", [("feat-atlas", "feat/parser"), ("ho-b15", "feat/co-ATLAS")])
def test_worktree_name_or_branch_beats_main_repository(material, name, branch):
    folder = worktree(material, name, branch)
    kept, _ = messages(material, material.projects, folder / "src/x.py")
    assert [m["cwd"] for m in kept] == [str(material.atlas)]


def test_pruned_worktree_path_matches_mapped_project_name(material):
    target = material.scratch / "feat-atlas/src/x.py"
    kept, _ = messages(material, material.projects, target)
    assert [m["cwd"] for m in kept] == [str(material.atlas)]


@pytest.mark.parametrize("kind", ["codex", "claude-code"])
@pytest.mark.parametrize("pruned", [False, True])
def test_temporary_worktree_session_is_attributed(material, kind, pruned):
    folder = material.scratch / "feat-atlas" if pruned else worktree(material, "feat-atlas")
    kept, counts = messages(material, folder, folder / "src/x.py", kind=kind)
    assert [(m["cwd"], m["typed_in"]) for m in kept] == [(str(material.atlas), str(folder))]
    assert counts["attributed"] == 1 and counts["excluded"] == {}


def test_temporary_worktree_session_without_name_tie_uses_main_repository(material):
    folder = worktree(material)
    kept, _ = messages(material, folder, folder / "src/x.py")
    assert [(m["cwd"], m["typed_in"]) for m in kept] == [(str(material.repo), str(folder))]


@pytest.mark.parametrize("name", ["api", "atlas2", "myatlas", "atlaswork"])
def test_short_names_and_partial_tokens_do_not_match(material, name):
    short = material.projects / "api"
    short.mkdir()
    material.folders[str(short)] = "projects/api.md"
    folder = worktree(material, f"feat-{name}", f"feat/co-{name}")
    kept, _ = messages(material, material.projects, folder / "src/x.py")
    assert [m["cwd"] for m in kept] == [str(material.repo)]


def test_main_repository_basename_never_matches_another_page(material):
    other = material.projects / "nested/meridian"
    other.mkdir(parents=True)
    material.folders[str(other)] = "projects/other.md"
    folder = worktree(material, "feat-meridian", "feat/co-meridian")
    kept, _ = messages(material, material.projects, folder / "src/x.py")
    assert [m["cwd"] for m in kept] == [str(material.repo)]


def test_normal_project_message_keeps_original_folder(material):
    folder = worktree(material, "feat-atlas")
    kept, counts = messages(material, material.repo, folder / "src/x.py")
    assert [m["cwd"] for m in kept] == [str(material.repo)]
    assert all("typed_in" not in m for m in kept)
    assert counts["attributed"] == 0 and counts["excluded"] == {}


def test_unrelated_temporary_session_stays_excluded(material):
    folder = material.scratch / "unrelated"
    folder.mkdir(parents=True)
    kept, counts = messages(material, folder, material.repo / "src/x.py")
    assert kept == []
    assert counts["excluded"] == {"temporary execution directory": 1}


@pytest.mark.parametrize("name", ["api", "atlas2", "myatlas"])
def test_pruned_worktree_name_requires_a_long_whole_token(material, name):
    short = material.projects / "api"
    short.mkdir()
    material.folders[str(short)] = "projects/api.md"
    kept, counts = messages(material, material.scratch / f"feat-{name}",
                            material.scratch / f"feat-{name}/src/x.py")
    assert kept == []
    assert counts["excluded"] == {"temporary execution directory": 1}


@pytest.mark.parametrize("location", ["scratch", "rem"])
def test_worktree_main_repository_must_be_usable(material, location):
    material.repo = getattr(material, location) / "meridian"
    (material.repo / ".git").mkdir(parents=True)
    folder = worktree(material)
    kept, counts = messages(material, material.projects, folder / "src/x.py")
    assert kept == []
    assert counts["excluded"] == {project_material.CONTAINER: 1}


@pytest.mark.parametrize("location", ["scratch", "rem", "missing"])
def test_worktree_name_tie_requires_a_usable_page_folder(material, location):
    material.folders.clear()
    base = material.projects / "missing" if location == "missing" else getattr(material, location)
    atlas = base / "atlas"
    if location != "missing":
        atlas.mkdir(parents=True)
    material.folders[str(atlas)] = "projects/atlas.md"
    folder = worktree(material, "feat-atlas")
    kept, _ = messages(material, material.projects, folder / "src/x.py")
    assert [m["cwd"] for m in kept] == [str(material.repo)]


def test_worktree_evidence_counts_each_call_once_and_ignores_output(material):
    folder = worktree(material, "feat-atlas")
    path = material.sessions / "rollout-counts.jsonl"
    codex_session(path, str(material.projects), [
        ("Fix the parser.", 2, [("shell", {"paths": [str(folder / f"src/x{i}.py") for i in range(5)]}),
                               ("output", str(material.repo / "src/x.py"))]),
        ("Then the docs.", 1, [("shell", {"file_path": str(material.repo / "README.md")})]),
        ("Continue.", 0.5, []),
        ("One more fix.", 0.4, [("shell", {"file_path": str(material.repo / "src/x.py")})]),
        ("That is all.", 0.3, []),
    ])
    calls = project_material._evidence(path, "codex", str(material.projects),
                                       project_material._Owners(material.folders, material.rem))
    assert [folders for _, folders, _ in calls] == [{str(material.atlas)}, {str(material.repo)},
                                                   {str(material.repo)}]
    kept, _ = project_material.session_messages(
        {"source": {"kind": "codex", "root": str(material.sessions)}}, since=NOW - timedelta(days=7),
        rem_root=material.rem, folders=material.folders)
    assert [m["cwd"] for m in kept] == [str(material.atlas), str(material.repo), str(material.repo),
                                      str(material.repo), str(material.repo)]


def test_an_exec_session_is_not_read_for_the_owners_words(material, monkeypatch):
    """2026-10-20: a fresh map read 2,561 exec and subagent sessions in full for nothing."""
    import json
    path = material.sessions / "rollout-exec.jsonl"
    codex_session(path, str(material.repo), [("A program-written prompt.", 1, [])])
    rows = path.read_text().splitlines()
    meta = json.loads(rows[0])
    meta["payload"].update(source="exec", originator="codex_exec")
    path.write_text("\n".join([json.dumps(meta), *rows[1:]]) + "\n")
    lines = []
    monkeypatch.setattr(project_material.json, "loads", lambda text, real=json.loads: lines.append(1) or real(text))
    found, _ = project_material.session_messages({"source": {"kind": "codex", "root": str(material.sessions)}},
                                                 since=NOW - timedelta(days=7), rem_root=material.rem,
                                                 folders=material.folders)
    assert found == [] and len(lines) == 1   # the first line only


def test_each_folder_is_asked_for_git_once(material, monkeypatch):
    """2026-10-20: 37,742 named paths walked their parents with two stats each (517k stats, 617 s)."""
    from pathlib import Path
    owners = project_material._Owners(material.folders, material.rem)
    asked = []
    real = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda self: asked.append(self) or real(self))
    for name in ("a.py", "b.py", "c/d.py"):
        owners.worktree(str(material.repo / "src" / name))
    gits = [path for path in asked if path.name == ".git"]
    assert len(gits) == len(set(gits))
