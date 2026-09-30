"""One page per repository, and folders that are not projects stay out (#1974).

On the owner's notebook connectonion was two pages (its `.claude/worktrees/*`
on one, the main checkout and `~/projects/.worktree/*` on the other), browser
too; a Codex chat named after its first prompt and two plugin-install folders
were projects; and `Paths` listed 49 worktrees.
"""

import json
from pathlib import Path

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.map import build_map, file_project, project_groups
from connectonion.rem.merge import aliases
from connectonion.rem.scan import main_checkout, not_a_project, scan_projects


def repo(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


def linked_worktree(path: Path, home: Path) -> Path:
    path.mkdir(parents=True)
    (path / ".git").write_text(f"gitdir: {home}/.git/worktrees/{path.name}\n")
    return path


def row(path, sessions=3, turns=None, repo_path="", origin=""):
    return {"path": str(path), "sessions": sessions, "turns": turns, "repo": str(repo_path or ""),
            "origin": origin, "first": "2026-09-01", "last": "2026-09-20"}


def test_a_removed_worktree_folder_belongs_to_the_repository_beside_it(tmp_path):
    projects = tmp_path / "projects"
    browser = repo(projects / "browser")
    repo(projects / "connectonion")
    assert main_checkout(str(projects / ".worktree/browser-139")) == str(browser)
    assert main_checkout(str(projects / ".worktree/connectonion-1.8-plan")) == str(projects / "connectonion")
    assert main_checkout(str(projects / ".worktree/wiki-home")) == ""        # no such repository: not guessed
    assert main_checkout(str(browser / ".worktrees/fix-tls")) == str(browser)
    live = linked_worktree(projects / ".worktree/co-ai-card", projects / "connectonion")
    assert main_checkout(str(live)) == str(projects / "connectonion")


def test_folders_that_are_not_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    home = tmp_path / "home"
    chat = home / "Documents/Codex/2026-08-17/create-a-scheduled-task-called-weekday"
    assert not_a_project(row(home)) == "home directory"
    assert not_a_project(row(tmp_path)) == "home directory"                   # above home
    assert not_a_project(row(chat, sessions=1, turns=1)) == "one short session outside a repository"
    assert not_a_project(row(chat, sessions=1, turns=9)) == ""                # a long conversation is work
    assert not_a_project(row(chat, sessions=2, turns=None)) == ""             # came back to it
    assert not_a_project(row(chat, sessions=1, turns=None)) == ""             # not counted: kept
    assert "hidden folder" in not_a_project(row(home / ".claude/plugins/cache/linear", sessions=4))
    assert "hidden folder" in not_a_project(row(home / "projects/.artifacts/live/host", sessions=2))
    assert not_a_project(row(home / ".claude/scheduled-tasks/daily", sessions=5)) == "scheduled-task folder"
    code = repo(home / "projects/one")
    assert not_a_project(row(code, sessions=1, turns=1, repo_path=code)) == ""  # a repository is a project
    assert not_a_project(row(home / ".codex/worktrees/ab12/one", sessions=1, turns=1,
                             repo_path=home / ".codex/worktrees/ab12/one")) == ""


def test_scan_counts_turns_only_for_a_lone_session_outside_a_repository(tmp_path, monkeypatch):
    monkeypatch.setattr("connectonion.rem.scan.project_exclusion", lambda path: "")  # tmp_path is a temp dir
    chat = tmp_path / "chat"
    chat.mkdir()
    sessions = tmp_path / "claude/p"
    sessions.mkdir(parents=True)
    typed = [{"type": "user", "cwd": str(chat), "sessionId": "s", "timestamp": f"2026-09-2{i}T00:00:00Z",
              "message": {"content": f"message {i}"}} for i in range(2)]
    (sessions / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in typed))
    rows = scan_projects({"claude-code": {"kind": "claude-code", "root": str(tmp_path / "claude")}}, 36500)
    assert [(r["path"], r["sessions"], r["turns"]) for r in rows] == [(str(chat), 1, 2)]


def test_worktrees_fold_into_their_repository_and_are_counted(tmp_path):
    home = repo(tmp_path / "projects/connectonion")
    agent = linked_worktree(home / ".claude/worktrees/agent-a1", home)
    other = linked_worktree(tmp_path / "projects/.worktree/connectonion-wiki", home)
    chat = tmp_path / "Documents/Codex/2026-08-17/pls"
    dropped = []
    groups = project_groups([row(home, repo_path=home, origin="git@github.com:o/connectonion.git"),
                             row(agent, repo_path=home, origin="git@github.com:o/connectonion.git"),
                             row(other, repo_path=home, origin="https://github.com/o/connectonion"),
                             row(chat, sessions=1, turns=1)], dropped)
    assert list(groups) == ["github.com/o/connectonion"]
    group = groups["github.com/o/connectonion"]
    assert group["paths"] == [str(home)] and group["worktrees"] == 2 and group["sessions"] == 9
    assert dropped == [{"path": str(chat), "sessions": 1, "reason": "one short session outside a repository"}]


def test_split_pages_for_one_repository_merge_into_the_written_one(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    home = repo(tmp_path / "projects/connectonion")
    agent = linked_worktree(home / ".claude/worktrees/agent-a1", home)
    nb.stub_project("projects/connectonion-aaa.md", "connectonion", [str(agent), str(home / ".claude/worktrees/gone")])
    written = nb.read("projects/connectonion-aaa.md").replace(
        "## What it is\n- Unknown — not investigated yet", "## What it is\n- An agent framework [1]").replace(
        "- (none yet)", "- [1] a session").replace("not investigated yet\n", "written 2026-09-30 (own messages)\n")
    nb.write("projects/connectonion-aaa.md", written)
    nb.stub_project("projects/connectonion-bbb.md", "connectonion", [str(home)])
    nb.write("projects/connectonion-bbb.md", nb.read("projects/connectonion-bbb.md").replace(
        "## Open threads\n- Unknown — not investigated yet", "## Open threads\n- Ship 1.9 [1]").replace(
        "- (none yet)", "- [1] another session"))
    material = root / ".state/projects/connectonion-bbb"
    material.mkdir(parents=True)
    (material / "messages.jsonl").write_text(json.dumps({"source": "claude-code:s:1", "timestamp": "2026-09-29T00:00:00+00:00",
                                                         "tool": "claude-code", "cwd": str(home), "text": "hi"}) + "\n")
    nb.write("notes/see.md", "[page](../projects/connectonion-bbb.md)\n")
    group = {"name": "connectonion", "paths": [str(home)], "worktrees": 2, "sessions": 116,
             "first": "2026-09-01", "last": "2026-09-30"}
    record, created = file_project(nb, "github.com/o/connectonion", group)
    assert (record, created) == ("projects/connectonion-aaa.md", False)
    assert nb.list("projects") == ["projects/connectonion-aaa.md"]
    page = nb.read(record)
    assert "- An agent framework [1]" in page and "- Ship 1.9 [2]" in page and "- [2] another session" in page
    paths = page.split("## Paths\n", 1)[1].split("\n## ", 1)[0]
    assert paths.splitlines()[:2] == [f"- {home}", "- Worktrees: 2"] and "agent-a1" not in paths
    assert "merged 20" in page.splitlines()[-1] and "written 2026-09-30" in page.splitlines()[-1]
    assert aliases(root)["projects/connectonion-bbb.md"]["into"] == record
    assert (root / ".state/archived/projects/connectonion-bbb.md").is_file()
    assert "../projects/connectonion-aaa.md" in nb.read("notes/see.md")
    moved = (root / ".state/projects/connectonion-aaa/messages.jsonl").read_text()
    assert '"text": "hi"' in moved
    again = nb.read(record)
    assert file_project(nb, "github.com/o/connectonion", group) == (record, False)
    assert nb.read(record) == again                                            # a rerun changes nothing


def test_a_page_naming_another_live_repository_is_not_merged_away(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    one, two = repo(tmp_path / "one"), repo(tmp_path / "two")
    nb.stub_project("projects/both.md", "both", [str(one), str(two)])
    nb.stub_project("projects/one.md", "one", [str(one)])
    nb.write("projects/one.md", nb.read("projects/one.md").replace("not investigated yet", "investigated 2026-09-01 (x)"))
    file_project(nb, "one", {"name": "one", "paths": [str(one)], "sessions": 1, "first": "2026-09-01",
                             "last": "2026-09-01"})
    assert sorted(nb.list("projects")) == ["projects/both.md", "projects/one.md"]


def test_the_map_leaves_junk_folders_out_and_archives_their_mapped_pages(tmp_path, monkeypatch):
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    chat = str(tmp_path / "Documents/Codex/2026-08-17/linear-plugin-linear-openai-curated-remote")
    nb.stub_project("projects/linear-plugin.md", "linear-plugin", [chat])
    code = repo(tmp_path / "code")
    monkeypatch.setattr("connectonion.rem.map.scan_projects", lambda *a, **k: [
        row(chat, sessions=1, turns=1), row(code, repo_path=code)])
    skills = tmp_path / "installed"
    skills.mkdir()
    report = build_map(root, {}, {}, skill_directories=[skills])
    assert [r["paths"] for r in report["projects"]] == [[str(code)]]
    assert report["projects_dropped"][0]["path"] == chat
    assert "projects/linear-plugin.md" in report["archived"]
    assert any("not made projects" in line for line in report["coverage"])


def test_a_short_dated_scratch_folder_stays_with_the_rest_of_its_project(tmp_path):
    base = tmp_path / "Documents/Codex"
    dropped = []
    groups = project_groups([row(base / "2026-08-26/realtime-voice-chat", sessions=14),
                             row(base / "2026-08-23/realtime-voice-chat", sessions=1, turns=1)], dropped)
    assert len(groups) == 1 and dropped == []
    assert next(iter(groups.values()))["sessions"] == 15
