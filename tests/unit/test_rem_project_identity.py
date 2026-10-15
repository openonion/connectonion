"""One page per repository, and folders that are not projects stay out (#1974).

On the owner's notebook connectonion was two pages (its `.claude/worktrees/*`
on one, the main checkout and `~/projects/.worktree/*` on the other), browser
too; a Codex chat named after its first prompt and two plugin-install folders
were projects; and `Paths` listed 49 worktrees.
"""

import json
from pathlib import Path

import pytest

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.map import build_map, file_project, project_groups
from connectonion.rem.merge import aliases
from connectonion.rem.scan import ONE_OFF_TASK, main_checkout, not_a_project, scan_projects


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
    assert not_a_project(row(chat, sessions=1, turns=1)) == ONE_OFF_TASK
    assert not_a_project(row(chat, sessions=1, turns=9)) == ONE_OFF_TASK
    assert not_a_project(row(chat, sessions=2, turns=None)) == ONE_OFF_TASK
    assert not_a_project(row(chat, sessions=1, turns=None)) == ONE_OFF_TASK
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
    rows = scan_projects({"claude-code": {"kind": "claude-code", "root": str(tmp_path / "claude"), "consented": True}}, 36500)
    assert [(r["path"], r["sessions"], r["turns"]) for r in rows] == [(str(chat), 1, 2)]


@pytest.mark.parametrize("preamble", ["queue-operation", "mode", "bridge-session"])
def test_scan_discovers_claude_projects_after_a_metadata_preamble(tmp_path, monkeypatch, preamble):
    monkeypatch.setattr("connectonion.rem.scan.project_exclusion", lambda path: "")
    project = tmp_path / "project"
    project.mkdir()
    sessions = tmp_path / "claude" / "encoded-project"
    sessions.mkdir(parents=True)
    rows = [{"type": preamble},
            {"type": "user", "cwd": str(project), "sessionId": "s",
             "timestamp": "2026-10-01T00:00:00Z", "message": {"content": "work on this project"}}]
    (sessions / "s.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    projects = scan_projects({"claude-code": {"kind": "claude-code", "root": str(tmp_path / "claude"), "consented": True}}, 36500)
    assert [(p["path"], p["sessions"], p["turns"]) for p in projects] == [(str(project), 1, 1)]


def test_scan_skips_a_claude_session_without_a_working_directory(tmp_path):
    sessions = tmp_path / "claude" / "encoded-project"
    sessions.mkdir(parents=True)
    (sessions / "s.jsonl").write_text('{"type": "queue-operation"}\n{"type": "mode"}\n', encoding="utf-8")
    assert scan_projects({"claude-code": {"kind": "claude-code", "root": str(tmp_path / "claude"), "consented": True}}, 36500) == []


@pytest.mark.parametrize("preamble_count, expected", [(255, 1), (256, 0)])
def test_claude_project_discovery_stops_after_a_bounded_preamble(tmp_path, monkeypatch, preamble_count, expected):
    monkeypatch.setattr("connectonion.rem.scan.project_exclusion", lambda path: "")
    project = tmp_path / "project"
    project.mkdir()
    sessions = tmp_path / "claude" / "encoded-project"
    sessions.mkdir(parents=True)
    message = {"type": "user", "cwd": str(project), "sessionId": "s",
               "timestamp": "2026-10-01T00:00:00Z", "message": {"content": "work on this project"}}
    (sessions / "s.jsonl").write_text('{"type": "mode"}\n' * preamble_count + json.dumps(message) + "\n",
                                     encoding="utf-8")
    projects = scan_projects({"claude-code": {"kind": "claude-code", "root": str(tmp_path / "claude"), "consented": True}}, 36500)
    assert [p["path"] for p in projects] == [str(project)] * expected


def test_claude_project_discovery_stops_after_its_byte_budget(tmp_path):
    sessions = tmp_path / "claude" / "encoded-project"
    sessions.mkdir(parents=True)
    preamble = {"type": "queue-operation", "content": "x" * 1_000_000}
    message = {"type": "user", "cwd": str(tmp_path / "project"), "sessionId": "s"}
    (sessions / "s.jsonl").write_text(json.dumps(preamble) + "\n" + json.dumps(message) + "\n", encoding="utf-8")
    assert scan_projects({"claude-code": {"kind": "claude-code", "root": str(tmp_path / "claude"), "consented": True}}, 36500) == []


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
    assert dropped == [{"path": str(chat), "sessions": 1, "reason": ONE_OFF_TASK}]


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
    from datetime import datetime, timezone
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    chat = str(tmp_path / "Documents/Codex/2026-08-17/linear-plugin-linear-openai-curated-remote")
    nb.stub_project("projects/linear-plugin.md", "linear-plugin", [chat])
    code = repo(tmp_path / "code")
    monkeypatch.setattr("connectonion.rem.map.scan_projects", lambda *a, **k: [
        row(chat, sessions=1, turns=1), row(code, repo_path=code)])
    message = {"source": "codex:task:100", "tool": "codex", "timestamp": datetime.now(timezone.utc).isoformat(),
               "cwd": chat, "text": "Install the plugin."}
    monkeypatch.setattr("connectonion.rem.project_material.session_messages",
                        lambda *a, **kw: ([message], {"files": 1, "harness": 0, "unfamiliar": 0, "excluded": {}}))
    skills = tmp_path / "installed"
    skills.mkdir()
    report = build_map(root, {}, {}, skill_directories=[skills])
    assert [r["paths"] for r in report["projects"]] == [[str(code)]]
    assert report["projects_dropped"][0]["path"] == chat
    assert "projects/linear-plugin.md" in report["archived"]
    assert any("not made projects" in line for line in report["coverage"])


def test_a_short_dated_scratch_folder_stays_with_the_rest_of_its_project(tmp_path):
    base = tmp_path / "Documents/Codex"
    for date in ("2026-08-26", "2026-08-23"):
        project = base / date / "acme-project"
        project.mkdir(parents=True)
        (project / "package.json").write_text('{"name": "acme-project"}')
    dropped = []
    groups = project_groups([row(base / "2026-08-26/acme-project", sessions=14),
                             row(base / "2026-08-23/acme-project", sessions=1, turns=1)], dropped)
    assert len(groups) == 1 and dropped == []
    assert next(iter(groups.values()))["sessions"] == 15


def test_client_documents_join_the_repository_and_its_worktree(tmp_path):
    code = repo(tmp_path / "code/acmewidget")
    tree = linked_worktree(tmp_path / "code/acmewidget-invoices", code)
    documents = tmp_path / "Documents/Acmewidget"
    documents.mkdir(parents=True)
    documents_row = {**row(documents, sessions=30), "first": "2026-08-01", "last": "2026-09-30"}
    groups = project_groups([documents_row, row(code, repo_path=code), row(tree, repo_path=code)])
    assert list(groups) == [str(code)]
    assert groups[str(code)] == {"name": "acmewidget", "paths": [str(code), str(documents)],
                                 "worktrees": 1, "sessions": 36, "first": "2026-08-01", "last": "2026-09-30"}


@pytest.mark.parametrize("name, copies", [("acmewidget", 2), ("abc", 1)])
def test_documents_need_one_repository_and_a_name_of_at_least_four_characters(tmp_path, name, copies):
    documents = tmp_path / "Documents" / name.title()
    documents.mkdir(parents=True)
    codes = [repo(tmp_path / str(number) / name) for number in range(copies)]
    groups = project_groups([row(documents), *(row(code, repo_path=code) for code in codes)])
    assert len(groups) == copies + 1
    assert groups[str(documents)]["paths"] == [str(documents)]
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    for identity, group in groups.items():
        file_project(notebook, identity, group)
    assert len(notebook.list("projects")) == copies + 1


def test_a_same_named_folder_inside_another_repository_is_not_plain(tmp_path):
    code = repo(tmp_path / "code/acmewidget")
    parent = repo(tmp_path / "other")
    folder = parent / "Acmewidget"
    folder.mkdir()
    assert len(project_groups([row(folder), row(code, repo_path=code)])) == 2


@pytest.mark.parametrize("repository_row", [True, False])
@pytest.mark.parametrize("written", ["documents", "code"])
def test_client_document_and_code_pages_merge_and_keep_the_most_written(tmp_path, repository_row, written):
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    code = repo(tmp_path / "code/acmewidget")
    documents = tmp_path / "Documents/Acmewidget"
    documents.mkdir(parents=True)
    nb.stub_project("projects/documents.md", "Acmewidget", [str(documents)])
    nb.stub_project("projects/code.md", "acmewidget", [str(code)])
    kept = f"projects/{written}.md"
    nb.write(kept, nb.read(kept).replace("## What it is\n", "## What it is\n- Client invoicing and contracts. [1]\n"))
    path = code if repository_row else documents
    group = {"name": path.name, "paths": [str(path)], "sessions": 30,
             "first": "2026-09-01", "last": "2026-09-30"}
    record, created = file_project(nb, str(path), group)
    assert (record, created) == (kept, False)
    assert nb.list("projects") == [kept]
    from connectonion.rem.investigate import project_paths
    assert set(project_paths(nb.read(kept))) == {str(code), str(documents)}
    old = "projects/code.md" if written == "documents" else "projects/documents.md"
    assert aliases(root)[old]["into"] == kept
    assert (root / ".state/archived" / old).is_file()


def test_a_document_page_gets_the_missing_repository_path_without_a_second_page(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    code = repo(tmp_path / "code/acmewidget")
    documents = tmp_path / "Documents/Acmewidget"
    documents.mkdir(parents=True)
    nb.stub_project("projects/documents.md", "Acmewidget", [str(documents)])
    record, created = file_project(nb, str(code), {"name": code.name, "paths": [str(code)], "sessions": 3,
                                                 "first": "2026-09-01", "last": "2026-09-20"})
    assert (record, created) == ("projects/documents.md", False)
    assert nb.list("projects") == [record]
    assert str(code) in nb.read(record) and str(documents) in nb.read(record)


def test_existing_same_named_repositories_do_not_claim_a_plain_folder(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    nb = Notebook(root)
    for number in range(2):
        code = repo(tmp_path / str(number) / "acmewidget")
        nb.stub_project(f"projects/code-{number}.md", "acmewidget", [str(code)])
    documents = tmp_path / "Documents/Acmewidget"
    documents.mkdir(parents=True)
    record, created = file_project(nb, str(documents), {"name": documents.name, "paths": [str(documents)],
                                                      "sessions": 30, "first": "2026-09-01", "last": "2026-09-30"})
    assert created and len(nb.list("projects")) == 3
    assert str(documents) in nb.read(record)
