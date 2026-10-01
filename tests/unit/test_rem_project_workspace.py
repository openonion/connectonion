"""Workspace sessions filed by the repository they worked in, and pages for new folders (#1943, stage 2b).

The owner's `~/projects` holds many repositories; 590 of 1,359 typed messages
(43%) were typed there and reached no page, because the map rightly never makes
a workspace a project. The session itself says where it worked: every tool call
names its paths. These fixtures are real session shapes -- Codex rollouts with
`turn_context`, `exec` custom tool calls and `function_call`s, Claude Code
transcripts with `tool_use` blocks and a `cwd` on every row -- in a temporary
workspace, never the operator's store.
"""

import json
import os
import stat
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from connectonion.rem import project_material
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.project_material import extract, stored

NOW = datetime.now(timezone.utc)
CONTAINER = "multi-repository workspace container"


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


# ---- Codex: session_meta, then turns of typed message, turn_context, tool calls ----

def codex_session(path: Path, cwd: str, turns, *, session=""):
    """turns: (text, days_ago, calls); a call is ("exec", js) | ("shell", {args}) |
    ("cwd", folder) for a turn_context that moved | ("output", text) for a tool's output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "session_meta", "payload": {"id": session or path.stem, "cwd": cwd,
                                                  "originator": "codex_cli_rs"}}]
    for number, (text, days, calls) in enumerate(turns):
        when = ago(days)
        # As in a real rollout, the turn's context (and the folder it runs in)
        # comes just before the message that opens the turn.
        moved = next((value for kind, value in calls if kind == "cwd"), cwd)
        rows.append({"timestamp": when, "type": "turn_context",
                     "payload": {"cwd": moved, "turn_id": f"t{number}", "workspace_roots": [cwd]}})
        rows.append({"timestamp": when, "type": "response_item", "payload": {
            "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}})
        for index, (kind, value) in enumerate(calls):
            call = f"c{number}-{index}"
            if kind == "exec":
                rows.append({"timestamp": when, "type": "response_item", "payload": {
                    "type": "custom_tool_call", "id": call, "call_id": call, "name": "exec", "status": "completed",
                    "input": value, "internal_chat_message_metadata_passthrough": {}}})
            elif kind == "shell":
                rows.append({"timestamp": when, "type": "response_item", "payload": {
                    "type": "function_call", "name": "shell", "call_id": call, "arguments": json.dumps(value)}})
            elif kind == "output":
                rows.append({"timestamp": when, "type": "response_item", "payload": {
                    "type": "custom_tool_call_output", "call_id": call, "output": value}})
        rows.append({"timestamp": when, "type": "response_item", "payload": {
            "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done."}]}})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def exec_command(cmd: str, workdir: str = "") -> str:
    """What Codex's `exec` tool input looks like: JavaScript calling tools.exec_command."""
    args = {"cmd": cmd, **({"workdir": workdir} if workdir else {}), "yield_time_ms": 1000}
    return f"const r = await tools.exec_command({json.dumps(args)}); text(r.output);\n"


# ---- Claude Code: a row per event, each carrying the cwd its shell is in ----

def claude_session(path: Path, turns, *, session="sess-1"):
    """turns: (cwd_typed_in, text, days_ago, calls); a call is (tool, input, row_cwd)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "file-history-snapshot", "messageId": "m0", "snapshot": {}}]
    for number, (cwd, text, days, calls) in enumerate(turns):
        when = ago(days)
        rows.append({"type": "user", "timestamp": when, "cwd": cwd, "sessionId": session, "uuid": f"u{number}",
                     "userType": "external", "message": {"role": "user", "content": text}})
        for index, (tool, arguments, row_cwd) in enumerate(calls):
            use = f"toolu_{number}_{index}"
            rows.append({"type": "assistant", "timestamp": when, "cwd": row_cwd, "sessionId": session,
                         "uuid": f"a{number}-{index}", "userType": "external",
                         "message": {"role": "assistant", "content": [
                             {"type": "tool_use", "id": use, "name": tool, "input": arguments}]}})
            rows.append({"type": "user", "timestamp": when, "cwd": row_cwd, "sessionId": session,
                         "uuid": f"r{number}-{index}", "userType": "external",
                         "message": {"role": "user", "content": [
                             {"type": "tool_result", "tool_use_id": use, "content": "ok"}]}})
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def ws(tmp_path, monkeypatch):
    """A workspace like ~/projects: CLAUDE.md, no .git, several repositories."""
    home = tmp_path / "home"
    projects = home / "projects"
    for repo in ("alpha", "beta", "gamma"):
        (projects / repo / ".git").mkdir(parents=True)
        (projects / repo / "src").mkdir()
    (projects / "CLAUDE.md").write_text("# a workspace of many repositories\n")
    (projects / "loose").mkdir()  # a folder with no .git and no page: not a project
    worktree = projects / "alpha/.claude/worktrees/fix"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {projects}/alpha/.git/worktrees/fix\n")
    # pytest's tmp_path lives in the system temporary folder, which the scanner
    # skips; everything else about the rule is the real one.
    real = project_material.project_exclusion
    monkeypatch.setattr(project_material, "project_exclusion",
                        lambda path: "" if (why := real(path)) == "temporary execution directory" else why)
    assert real(projects) == CONTAINER
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_project("projects/alpha.md", "alpha", [str(projects / "alpha")])
    codex_root, claude_root = tmp_path / "codex", tmp_path / "claude"
    subs = {"codex": {"kind": "codex", "root": str(codex_root), "enabled": True},
            "claude-code": {"kind": "claude-code", "root": str(claude_root), "enabled": True}}
    return types.SimpleNamespace(root=root, notebook=notebook, projects=projects, codex=codex_root,
                                 claude=claude_root, subs=subs, p=lambda rel: str(projects / rel))


def texts(root, record):
    return [m["text"] for m in stored(root, record)]


def test_a_codex_session_typed_in_the_workspace_is_filed_under_the_repository_its_tools_touched(ws):
    codex_session(ws.codex / "2026/09/28/rollout-a.jsonl", str(ws.projects), [
        ("Make alpha's parser strict.", 2, [("exec", exec_command("sed -n 1,80p " + ws.p("alpha/src/parse.py"))),
                                            ("exec", exec_command("pytest -q", workdir=ws.p("alpha")))]),
    ])
    report = extract(ws.root, ws.subs)
    assert texts(ws.root, "projects/alpha.md") == ["Make alpha's parser strict."]
    kept = stored(ws.root, "projects/alpha.md")[0]
    assert kept["cwd"] == ws.p("alpha") and kept["typed_in"] == str(ws.projects)
    assert report["workspace"] == {"attributed": 1, "folders": 1, "stayed_out": 0}
    assert CONTAINER not in report["excluded"]
    assert "parser" not in json.dumps(report)  # counts and paths, never what was said


def test_a_claude_code_session_counts_reads_edits_and_a_relative_cd(ws):
    claude_session(ws.claude / "-home-projects/s.jsonl", [
        (str(ws.projects), "Beta's release notes are wrong; fix them.", 1, [
            ("Read", {"file_path": ws.p("beta/src/NOTES.md")}, str(ws.projects)),
            ("Bash", {"command": "cd beta && git status", "description": "status"}, str(ws.projects)),
            ("Edit", {"file_path": ws.p("beta/src/NOTES.md"), "old_string": "a", "new_string": "b"},
             ws.p("beta")),
        ]),
    ])
    report = extract(ws.root, ws.subs)
    record = next(r for r in ws.notebook.list("projects") if r != "projects/alpha.md")
    assert texts(ws.root, record) == ["Beta's release notes are wrong; fix them."]
    assert report["workspace"]["attributed"] == 1


def test_a_session_that_moved_between_repositories_is_split_per_message(ws):
    codex_session(ws.codex / "2026/09/28/rollout-m.jsonl", str(ws.projects), [
        ("first alpha", 3, [("exec", exec_command("cat " + ws.p("alpha/src/a.py"))),
                            ("exec", exec_command("ls " + ws.p("alpha/src")))]),
        ("then beta", 2.9, [("shell", {"command": ["bash", "-lc", "git -C beta log -3"]}),
                          ("cwd", ws.p("beta"))]),
        # No tools in this turn: it goes where the whole session worked most (alpha: 2 calls, beta: 2 --
        # a tie, and the folder touched first wins).
        ("thanks, that is all", 2.8, []),
    ])
    extract(ws.root, ws.subs)
    beta = next(r for r in ws.notebook.list("projects") if r != "projects/alpha.md")
    assert texts(ws.root, "projects/alpha.md") == ["first alpha", "thanks, that is all"]
    assert texts(ws.root, beta) == ["then beta"]


def test_a_turn_without_tools_follows_the_repository_the_session_worked_in_most(ws):
    codex_session(ws.codex / "2026/09/28/rollout-q.jsonl", str(ws.projects), [
        ("what is left to do?", 2, []),
        ("fix gamma", 1.9, [("exec", exec_command("pytest", workdir=ws.p("gamma"))),
                          ("exec", exec_command("cat " + ws.p("gamma/src/x.py")))]),
        ("and one alpha thing", 1.8, [("exec", exec_command("cat " + ws.p("alpha/src/y.py")))]),
    ])
    extract(ws.root, ws.subs)
    gamma = next(r for r in ws.notebook.list("projects") if r.startswith("projects/gamma"))
    assert texts(ws.root, gamma) == ["what is left to do?", "fix gamma"]
    assert texts(ws.root, "projects/alpha.md") == ["and one alpha thing"]


def test_a_session_that_points_at_no_repository_stays_out(ws):
    codex_session(ws.codex / "2026/09/28/rollout-n.jsonl", str(ws.projects), [
        ("which of these repos should I work on?", 1, [
            ("exec", exec_command("ls " + str(ws.projects))),
            ("exec", exec_command("cat " + ws.p("CLAUDE.md"))),
            ("exec", exec_command("ls " + ws.p("loose") + " /usr/bin")),
            # A tool's output naming a repository is not something the session did there.
            ("output", "see " + ws.p("beta/src/NOTES.md")),
        ]),
    ])
    claude_session(ws.claude / "-home-projects/n.jsonl", [
        (str(ws.projects), "draft a tweet", 1, [
            # The text an edit writes is not a path it touched.
            ("Write", {"file_path": "/elsewhere/tweet.md", "content": "see " + ws.p("beta/src/x.py")},
             str(ws.projects)),
        ]),
    ], session="sess-n")
    before = set(ws.notebook.list("projects"))
    report = extract(ws.root, ws.subs)
    assert report["excluded"] == {CONTAINER: 2}
    assert report["workspace"] == {"attributed": 0, "folders": 0, "stayed_out": 2}
    assert set(ws.notebook.list("projects")) == before


def test_the_deepest_project_folder_wins(ws):
    ws.notebook.stub_project("projects/alpha-docs.md", "alpha-docs", [ws.p("alpha/docs")])
    codex_session(ws.codex / "2026/09/28/rollout-d.jsonl", str(ws.projects), [
        ("tidy the docs", 1, [("exec", exec_command("cat " + ws.p("alpha/docs/index.md")))]),
        ("work in the worktree", 1, [("exec", exec_command("git status",
                                                           workdir=ws.p("alpha/.claude/worktrees/fix")))]),
    ])
    extract(ws.root, ws.subs)
    assert texts(ws.root, "projects/alpha-docs.md") == ["tidy the docs"]
    # A linked worktree is a project folder of its own; with no page listing it,
    # the page of the repository that holds it is the deepest listed folder.
    kept = stored(ws.root, "projects/alpha.md")
    assert [m["text"] for m in kept] == ["work in the worktree"]
    assert kept[0]["cwd"] == ws.p("alpha/.claude/worktrees/fix")


def test_a_recent_folder_with_no_page_gets_the_maps_page_and_an_older_one_is_listed(ws):
    codex_session(ws.codex / "2026/09/28/rollout-b.jsonl", str(ws.projects), [
        ("beta work", 2, [("exec", exec_command("cat " + ws.p("beta/src/b.py")))])])
    codex_session(ws.codex / "2026/08/10/rollout-g.jsonl", str(ws.projects), [
        ("gamma work", 40, [("exec", exec_command("cat " + ws.p("gamma/src/g.py")))])])
    report = extract(ws.root, ws.subs)
    assert len(report["created"]) == 1
    record = report["created"][0]
    # The map's record name and stub, byte for byte: made by the same code.
    from connectonion.rem.map import _record
    assert record == _record("projects", "beta", ws.p("beta"))
    twin = Notebook(ws.root.parent / "twin")
    (ws.root.parent / "twin").mkdir()
    twin.stub_project(record, "beta", [ws.p("beta")], sessions=1, first_seen=ago(2)[:10], last_seen=ago(2)[:10])
    assert ws.notebook.read(record) == twin.read(record)
    assert "Investigation: mapped" in ws.notebook.read(record)
    assert texts(ws.root, record) == ["beta work"]
    assert [row["path"] for row in report["unmapped"]] == [ws.p("gamma")]
    assert not [r for r in ws.notebook.list("projects") if r.startswith("projects/gamma")]
    # File modes are what they always were: the page like any page, the material private.
    assert stat.S_IMODE(ws.notebook.path(record).stat().st_mode) == \
        stat.S_IMODE(ws.notebook.path("projects/alpha.md").stat().st_mode)
    folder = ws.root / ".state/projects" / Path(record).stem
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    for name in ("messages.md", "messages.jsonl", "state.json"):
        assert stat.S_IMODE((folder / name).stat().st_mode) == 0o600, name


def test_a_page_is_not_made_twice_on_the_next_run(ws):
    file = ws.codex / "2026/09/28/rollout-b.jsonl"
    codex_session(file, str(ws.projects), [("beta work", 2, [("exec", exec_command("ls " + ws.p("beta/src")))])])
    first = extract(ws.root, ws.subs)
    second = extract(ws.root, ws.subs, full=True)
    assert len(first["created"]) == 1 and second["created"] == []
    assert len(ws.notebook.list("projects")) == 2


def test_projects_says_what_was_attributed_created_and_left(ws, monkeypatch):
    from typer.testing import CliRunner

    from connectonion.cli.main import app
    home = Path(os.environ["HOME"])
    sessions = home / ".codex/sessions"
    codex_session(sessions / "2026/09/28/rollout-a.jsonl", str(ws.projects), [
        ("alpha work", 1, [("exec", exec_command("ls " + ws.p("alpha/src")))]),
        ("beta work", 1, [("exec", exec_command("ls " + ws.p("beta/src")))])])
    codex_session(sessions / "2026/08/10/rollout-g.jsonl", str(ws.projects), [
        ("gamma work", 40, [("exec", exec_command("ls " + ws.p("gamma/src")))])])
    codex_session(sessions / "2026/09/28/rollout-n.jsonl", str(ws.projects), [("hello", 1, [])])
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a, **k: pytest.fail("model called"))
    result = CliRunner().invoke(app, ["rem", "--root", str(ws.root), "projects"])
    assert result.exit_code == 0, result.output
    assert "3 typed in a workspace were filed under the repository they worked in" in result.stderr
    assert "1 stayed out" in result.stderr
    assert "made 1 project page for folders active in the last 14 days" in result.stderr
    assert "1 more folder with messages and no page; not created (older than 14 days)" in result.stdout
    result = CliRunner().invoke(app, ["rem", "--root", str(ws.root), "--json", "projects", "--full"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    body = data["data"]
    assert body["workspace"] == {"attributed": 3, "folders": 3, "stayed_out": 1}
    assert body["created"] == [] and [row["path"] for row in body["unmapped"]] == [ws.p("gamma")]


def test_inits_recent_projects_step_writes_a_workspace_attributed_project(ws, monkeypatch):
    """The first run (#1946) writes the projects active this fortnight; a repository
    worked in only from the workspace, with no page before, is one of them."""
    from connectonion.cli.commands.rem_commands import _first_pages, _first_project_rows
    from connectonion.rem.config import read_config
    home = Path(os.environ["HOME"])
    codex_session(home / ".codex/sessions/2026/09/28/rollout-b.jsonl", str(ws.projects), [
        ("beta needs a release", 1, [("exec", exec_command("git status", workdir=ws.p("beta")))])])
    written = []

    def write_page(root, record, **kw):
        written.append(record)
        return {"record": record, "changed": [record]}

    monkeypatch.setattr("connectonion.rem.project_pages.write_page", write_page)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter in tests"})
    ctx = types.SimpleNamespace(obj={"json": False, "root": ws.root})
    said = []
    result = _first_pages(ctx, ws.root, read_config(ws.root), said.append, lambda: "", people=[],
                          projects=_first_project_rows(ws.root, None), orgs=[])["project_pages"]
    beta = next(r for r in ws.notebook.list("projects") if r.startswith("projects/beta"))
    assert result["started"] and written[0] == beta  # the recent one first; older ones follow
    assert f"  {beta}: written" in said
    assert texts(ws.root, beta) == ["beta needs a release"]


def as_codex_desktop(path: Path) -> None:
    """Rewrite a codex_session file the way Codex Desktop writes it (#1978): the
    originator, every user-slot message under the metadata passthrough, and the
    client's AGENTS.md / environment block before the first typed message."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["payload"]["originator"] = "Codex Desktop"
    out = [rows[0], {"timestamp": rows[1]["timestamp"], "type": "response_item", "payload": {
        "type": "message", "role": "user", "id": "m-env",
        "content": [{"type": "input_text", "text": "# AGENTS.md instructions for " + rows[0]["payload"]["cwd"]}],
        "internal_chat_message_metadata_passthrough": {
            "turn_id": "t0", "create_time": 1.0,
            "content_item_kinds": ["agents_md.instructions", "environments.environment_context"]}}}]
    for row in rows[1:]:
        payload = row.get("payload", {})
        if payload.get("type") == "message" and payload.get("role") == "user":
            payload.update({"id": "m", "internal_chat_message_metadata_passthrough": {
                "turn_id": "t", "create_time": 1.0, "content_item_kinds": ["user.text"]}})
        out.append(row)
    path.write_text("".join(json.dumps(row) + "\n" for row in out), encoding="utf-8")


def test_a_codex_desktop_thread_typed_in_the_workspace_is_filed_by_its_tool_calls(ws):
    """Desktop threads were read as all-injected, so their workspace messages never
    reached attribution (#1978). They carry the same turn_context and exec calls."""
    path = ws.codex / "2026/09/28/rollout-desk.jsonl"
    codex_session(path, str(ws.projects), [
        ("alpha 的 parser 要严格一点。", 2, [("exec", exec_command("pytest -q", workdir=ws.p("alpha")))]),
        ("Now the beta README.", 1, [("exec", exec_command("sed -n 1,40p " + ws.p("beta/README.md")))]),
    ])
    as_codex_desktop(path)
    report = extract(ws.root, ws.subs)
    assert texts(ws.root, "projects/alpha.md") == ["alpha 的 parser 要严格一点。"]
    assert report["workspace"]["attributed"] == 2 and report["workspace"]["stayed_out"] == 0
    assert report["harness_blocks_skipped"] == 1  # the AGENTS.md block, never a page's material
