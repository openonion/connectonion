"""Synthetic owner conversations; imports never read the operator's transcripts."""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

import pytest
from typer.testing import CliRunner

from connectonion.rem import service
from connectonion.rem.config import prepare, set_config
from connectonion.rem.files import Notebook, RemError, maintenance_lock, read_json, state_path, write_json
from connectonion.rem.sessions import (import_sessions, mentions, read_summary, reader_fields,
                                      rewrite_session, summarise_line, summarise_sessions, summary_path)

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
STAMP = "2026-10-15T22:12:00Z"


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    root, transcripts = tmp_path / "notebook", tmp_path / "transcripts"
    prepare(root)
    set_config(root, ["schedule.timezone", "Australia/Sydney"])
    transcripts.mkdir()
    subscriptions = {kind: {"kind": kind, "root": str(transcripts / kind), "enabled": True, "consented": True}
                     for kind in ("codex", "claude-code")}
    monkeypatch.setattr(service, "subscriptions", lambda root: subscriptions)
    monkeypatch.setattr(service, "mail_available", lambda kind: False)
    return root, transcripts, subscriptions


def codex(text="Build a simple session reader\n# Keep this typed heading", *, role="user", stamp=STAMP):
    return {"type": "response_item", "timestamp": stamp,
            "payload": {"type": "message", "role": role,
                        "content": [{"type": "input_text" if role == "user" else "output_text", "text": text}]}}


def claude(text="Keep the reader simple", *, role="user", **fields):
    content = text if role == "user" else [{"type": "text", "text": text}]
    return {"type": role, "timestamp": STAMP, "sessionId": "claude-session", "cwd": "/work/demo",
            "entrypoint": "cli", "message": {"role": role, "content": content}, **fields}


def transcript(notebook, *, kind="codex", session="3456-abcdef12", cwd="/work/demo", rows=None, **meta):
    _, directory, _ = notebook
    path = directory / kind / ("rollout-" + session + ".jsonl" if kind == "codex" else session + ".jsonl")
    path.parent.mkdir(exist_ok=True)
    if rows is None:
        rows = [codex(), codex("The session reader is ready.", role="assistant")]
    if kind == "codex":
        rows = [{"type": "session_meta", "payload": {
            "id": session, "cwd": cwd, "source": "cli", "originator": "codex_cli_rs", **meta}}, *rows]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path


def test_rem_session_codex_page_and_openable_sources(notebook):
    root, _, _ = notebook
    path = transcript(notebook)
    report = import_sessions(root, now=NOW)
    assert report["imported"] == 1 and report["updated"] == 0 and report["skipped"] == {}
    book = Notebook(root)
    record, = book.list("sessions")
    assert record == "sessions/2026-10-16-build-a-simple-session-reader-abcdef12.md"
    page = book.read(record)
    assert page.startswith("# Build a simple session reader\n")
    assert "- Agent: Codex" in page and "- Turns: 1" in page
    assert "- Project: /work/demo" in page and "- Folder: /work/demo" in page
    assert "### 09:12\n> Build a simple session reader\n> # Keep this typed heading" in page
    assert "## Final reply\n> The session reader is ready." in page
    offset = len(path.read_bytes().splitlines(keepends=True)[0])
    source = f"codex:3456-abcdef12:{offset}"
    assert "## Sources\n- " + source in page
    from connectonion.rem.reader import snapshot, TEMPLATE
    data = snapshot(root, local=True)
    assert "sessions" in data["categories"] and "AI sessions" in TEMPLATE.read_text()
    assert data["source_context"][source]["excerpt"].startswith("Build a simple session reader")
    assert data["counts"]["sessions"] == {"mapped": 1, "written": 1}


@pytest.mark.parametrize("meta,reason", [
    ({"source": "exec"}, "exec_or_subagent"),
    ({"source": {"subagent": {"spawn": {}}}}, "exec_or_subagent"),
    ({"originator": "codex_exec"}, "exec_or_subagent"),
    ({"originator": "co_rem"}, "rem_task"),
    ({"cwd": "/notes/.state/tasks/run"}, "rem_task"),
    ({"cwd": "/private/tmp/codex-probe"}, "temporary_directory"),
])
def test_rem_session_automation_stays_out(notebook, meta, reason):
    transcript(notebook, **meta)
    result = import_sessions(notebook[0], now=NOW)
    assert result["skipped"] == {reason: 1}
    assert not Notebook(notebook[0]).list("sessions")


@pytest.mark.parametrize("fields,reason", [
    ({}, ""), ({"entrypoint": "sdk-cli"}, "program_prompt"),
    ({"promptSource": "system"}, "program_prompt"),
    ({"isSidechain": True}, "sidechain"), ({"isMeta": True}, "no_typed_message"),
    ({"cwd": "/notes/.state/tasks/run"}, "rem_task"),
])
def test_rem_session_claude_typed_and_program_prompts(notebook, fields, reason):
    transcript(notebook, kind="claude-code", rows=[claude(**fields), claude("Done", role="assistant")])
    report = import_sessions(notebook[0], now=NOW)
    assert report["skipped"] == ({reason: 1} if reason else {})
    if not reason:
        book = Notebook(notebook[0])
        page = book.read(book.list("sessions")[0])
        assert "- Agent: Claude Code" in page and "- Turns: 1" in page
        assert "> Keep the reader simple" in page and "> Done" in page
        assert "- claude-code:claude-session:0" in page


def test_rem_session_idempotent_append_and_changed_title_keep_the_record(notebook):
    root, _, _ = notebook
    path = transcript(notebook)
    assert import_sessions(root, now=NOW)["imported"] == 1
    record, = Notebook(root).list("sessions")
    again = import_sessions(root, now=NOW)
    assert again["imported"] == 0 and again["unchanged"] == 1
    with path.open("a") as stream:
        stream.write(json.dumps(codex("Use day headings", stamp="2026-10-16T13:12:00Z")) + "\n")
    updated = import_sessions(root, now=NOW)
    assert updated["updated"] == 1 and updated["imported"] == 0
    assert Notebook(root).list("sessions") == [record]
    assert "- Turns: 2" in Notebook(root).read(record)
    assert "### 2026-10-17 00:12" in Notebook(root).read(record)
    # A relocated copy is the same session, even if its opening title differs.
    transcript(notebook, session="3456-abcdef12", rows=[codex("A revised title")])
    import_sessions(root, now=NOW)
    assert Notebook(root).list("sessions") == [record]
    assert Notebook(root).read(record).startswith("# A revised title")
    progress = read_json(state_path(root, "sessions.json"), {})
    assert progress["sessions"]["codex:3456-abcdef12"] == record


def test_rem_session_project_link_uses_deepest_path(notebook):
    root, _, _ = notebook
    book = Notebook(root)
    book.stub_project("projects/work.md", "Work", paths=["/work"])
    book.stub_project("projects/demo.md", "Demo", paths=["/work/demo"])
    transcript(notebook, cwd="/work/demo/feature")
    import_sessions(root, now=NOW)
    record, = book.list("sessions")
    assert "- Project: [Demo](../projects/demo.md)" in book.read(record)
    from connectonion.rem.reader import snapshot
    row = next(r for r in snapshot(root)["records"] if r["path"] == record)
    assert row["session_project"] == "projects/demo.md"


@pytest.mark.parametrize("cwd,expected", [("/work", "Demo"), ("/work/other", "Other")])
def test_rem_session_codex_project_from_tool_calls(notebook, cwd, expected):
    root, _, _ = notebook
    book = Notebook(root)
    book.stub_project("projects/demo.md", "Demo", paths=["/work/demo"])
    book.stub_project("projects/other.md", "Other", paths=["/work/other"])
    calls = [
        {"type": "function_call", "arguments": json.dumps({"cmd": "cd demo && pwd", "workdir": "/work"})},
        {"type": "function_call", "arguments": json.dumps({"command": "cat /work/other/file.py"})},
        {"type": "custom_tool_call", "input": "*** Begin Patch\n*** Update File: /work/demo/app.py\n*** End Patch"},
        {"type": "custom_tool_call", "input": "cat /work/demo/README.md"},
    ]
    transcript(notebook, cwd=cwd, rows=[codex(), *({"type": "response_item", "payload": c} for c in calls)])
    import_sessions(root, now=NOW)
    page = book.read(book.list("sessions")[0])
    assert f"- Project: [{expected}](../projects/{expected.lower()}.md)" in page
    assert f"- Folder: {cwd}" in page
    from connectonion.rem.sessions import _read_session
    path, = (notebook[1] / "codex").iterdir()
    session, _ = _read_session(path, "codex", datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert session["touched"]["/work/demo"] == 1


def test_rem_session_claude_project_from_tool_inputs(notebook):
    root, _, _ = notebook
    book = Notebook(root)
    book.stub_project("projects/demo.md", "Demo", paths=["/work/demo"])
    book.stub_project("projects/other.md", "Other", paths=["/work/other"])
    call = claude(role="assistant", cwd="/work")
    call["message"]["content"] = [{"type": "tool_use", "input": {"file_path": path}}
                                   for path in ("/work/demo/a.py", "/work/demo/b.py", "/work/other/a.py")]
    sidechain = claude(role="assistant", cwd="/work", isSidechain=True)
    sidechain["message"]["content"] = [{"type": "tool_use", "input": {"file_path": "/work/other/a.py"}}] * 5
    transcript(notebook, kind="claude-code", rows=[claude(cwd="/work"), call, sidechain])
    import_sessions(root, now=NOW)
    page = book.read(book.list("sessions")[0])
    assert "- Project: [Demo](../projects/demo.md)" in page
    assert "- Folder: /work" in page


def test_rem_session_project_ties_unmapped_and_bounded_calls(notebook):
    from collections import Counter
    from connectonion.rem.sessions import _project, _touched
    session = {"cwd": "/work", "touched": Counter({"/work/other/a.py": 2, "/work/demo/a.py": 2})}
    assert _project(session, {"/work/other": "projects/z.md", "/work/demo": "projects/a.md"}) == "projects/a.md"
    assert _project(session, {}) is None
    paths = _touched("cd demo && cat /work/demo/a.py /work/demo/a.py "
                     "&& cd ~ && cd - && cd $HOME " + " " * 20_000 + "/work/other/a.py", "/work")
    assert paths == Counter({"/work/demo/a.py": 2, "/work/demo": 1})
    assert _touched(json.dumps({"cmd": "cd demo && pwd", "workdir": "/elsewhere"}), "/work") == Counter({
        "/elsewhere": 1, "/elsewhere/demo": 1})
    transcript(notebook, cwd="/work", rows=[codex(), {"type": "response_item", "payload": {
        "type": "function_call", "arguments": json.dumps({"cmd": "cat /unmapped/file.py"})}}])
    import_sessions(notebook[0], now=NOW)
    book = Notebook(notebook[0])
    assert "- Project: /work\n- Folder: /work" in book.read(book.list("sessions")[0])


def test_rem_session_format_change_renders_existing_pages(notebook):
    root, _, _ = notebook
    transcript(notebook)
    import_sessions(root, now=NOW)
    progress = read_json(state_path(root, "sessions.json"), {})
    progress["settings"].pop("format", None)
    write_json(state_path(root, "sessions.json"), progress)
    assert import_sessions(root, now=NOW)["updated"] == 1
    assert import_sessions(root, now=NOW)["unchanged"] == 1


def tool_call(name, value, *, custom=False, call=None):
    shape, field = ("custom_tool_call", "input") if custom else ("function_call", "arguments")
    return {"type": "response_item", "payload": {"type": shape, "name": name, "call_id": call,
            field: value if custom else json.dumps(value)}}


def tool_output(text, *, custom=False, call=None):
    return {"type": "response_item", "payload": {
        "type": "custom_tool_call_output" if custom else "function_call_output", "output": text, "call_id": call}}


def test_rem_session_codex_artifacts(notebook):
    root, _, _ = notebook
    secret = "sk-" + "a" * 30
    pr = "https://github.com/openonion/connectonion/pull/123"
    transcript(notebook, rows=[codex(),
        tool_call("apply_patch", "*** Begin Patch\n*** Update File: app.py\n*** End Patch", custom=True),
        tool_call("functions.apply_patch", {"patch": "*** Add File: reader.py", "workdir": "/work/feature"}),
        tool_call("exec_command", {"cmd": "cd /work/demo && git switch -c feat/x\ngit commit -m 'Add the reader'"}),
        tool_output(json.dumps({"output": "[feat/x 1a2b3c4] Add the reader\n 1 file changed"})),
        tool_output("[feat/x 1a2b3c4] Add the reader", custom=True),
        tool_call("exec_command", {"cmd": f"git push origin feat/x --token={secret}"}),
        tool_call("exec_command", {"cmd": "gh pr list"}, call="list"),
        tool_output("https://github.com/openonion/connectonion/pull/7", call="list"),
        tool_call("exec_command", {"cmd": f"gh pr create --body '{secret}'"}, call="create"),
        tool_output(pr + "\n" + pr, custom=True, call="create"),
        tool_call("exec_command", {"cmd": "gh pr view https://github.com/other/repo/pull/9"}),
        codex("Done.", role="assistant")])
    import_sessions(root, now=NOW)
    book = Notebook(root)
    page = book.read(book.list("sessions")[0])
    artifacts = page.split("## Artifacts\n")[1].split("## What you typed")[0]
    assert artifacts.count(pr) == 1 and "https://github.com/other/repo/pull/9" in artifacts  # command only
    assert "pull/7" not in artifacts  # listed, not this session's
    assert "- Pull requests: " + pr + "\n" in artifacts
    assert artifacts.count("- Commits: `1a2b3c4` Add the reader (feat/x)") == 1
    assert "- Branches: feat/x\n" in artifacts
    assert "- Files changed (2): /work/demo/app.py, /work/feature/reader.py" in artifacts
    assert "- Commands: 5 run; notable: `git commit -m 'Add the reader'`; `git push origin feat/x" in artifacts
    assert "`gh pr create --body '[secret-shaped text removed by co rem]'`" in artifacts
    assert secret not in page
    assert reader_fields(page)["session_artifacts"] == {"prs": 1, "commits": 1, "files": 2}


def test_rem_session_claude_artifacts_do_not_become_typed_messages(notebook):
    root, _, _ = notebook
    call = claude(role="assistant")
    call["message"]["content"] = [
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "app.py", "old_string": "old"}},
        {"type": "tool_use", "name": "Bash", "input": {"command": "cd /work/demo && git push origin feat/x"}}]
    result = claude()
    result["message"]["content"] = [{"type": "tool_result", "content": [
        {"type": "text", "text": "To github.com:openonion/connectonion.git\nfeat/x -> feat/x"}]}]
    sidechain = claude(role="assistant", isSidechain=True)
    sidechain["message"]["content"] = [{"type": "tool_use", "name": "Write", "input": {"file_path": "ignored.py"}}]
    transcript(notebook, kind="claude-code", rows=[claude(), call, result, sidechain, claude("Done", role="assistant")])
    import_sessions(root, now=NOW)
    book = Notebook(root)
    page = book.read(book.list("sessions")[0])
    assert "- Turns: 1" in page
    assert "- Files changed (1): /work/demo/app.py" in page
    assert "- Commands: 1 run; notable: `git push origin feat/x`" in page
    assert "ignored.py" not in page and "feat/x -> feat/x" not in page
    assert "### 09:12\n> Keep the reader simple" in page


def test_rem_session_artifact_caps_root_commits_and_json_outputs(notebook):
    root, _, _ = notebook
    pr = "https://github.com/openonion/connectonion/pull/1"
    commands = "git checkout -b feat/a\ngit branch feat/b\ngit branch -D ignored\n" \
               "git worktree add /work/tree -b feat/c\ngit commit -m 'fix; git push fictional'\n" \
               + "\n".join(f"gh pr view {n}" for n in range(15))
    patch = "\n".join(f"*** Update File: file{n}.py" for n in range(35))
    transcript(notebook, rows=[codex(), tool_call("exec_command", {"cmd": commands}),
        tool_call("apply_patch", patch, custom=True), tool_call("apply_patch", patch, custom=True),
        tool_call("exec_command", {"cmd": "gh pr create --fill"}, call="pr"),
        tool_output(json.dumps({"url": pr}), call="pr"),
        tool_output("\n".join(f"[feat/a {'%07x' % n}] Commit {n}" for n in range(22))),
        tool_output("[main (root-commit) abcdef0] Initial commit"),
        tool_output(" " * 20_000 + "https://github.com/ignored/repo/pull/2", call="pr"),
        tool_call("apply_patch", " " * 20_000 + "\n*** Update File: ignored.py", custom=True)])
    import_sessions(root, now=NOW)
    book = Notebook(root)
    page = book.read(book.list("sessions")[0])
    assert "- Pull requests: " + pr in page and "ignored/repo" not in page
    assert "- Branches: feat/a, feat/b, feat/c, main" in page and "Branches: ignored" not in page
    assert "- Files changed (35):" in page and "/work/demo/file29.py" in page
    assert "/work/demo/file30.py" not in page and "ignored.py" not in page
    assert "- … and 3 more commits" in page and page.count("- Commits:") == 20
    assert "`git commit -m 'fix; git push fictional'`" in page and "`git push fictional'`" not in page
    notable = page.split("; notable: ")[1].split("\n", 1)[0]
    assert notable.count("`gh pr view") == 11
    assert reader_fields(page)["session_artifacts"] == {"prs": 1, "commits": 23, "files": 35}


def test_rem_session_summary_and_rewrite_keep_raw_attachment(notebook):
    root, _, _ = notebook
    book = Notebook(root)
    book.write("people/ody.md", "# Ody\n\n## Facts\n")
    book.stub_project("projects/demo.md", "Demo", paths=["/work/demo"])
    transcript(notebook, rows=[codex("Older turn outside window", stamp="2025-01-01T00:00:00Z"),
        codex("Keep the reader simple\nDo not change the raw attachment."),
        codex("Ask Ody for feedback", stamp="2026-10-15T22:13:00Z"), codex("Ready.", role="assistant")])
    import_sessions(root, now=NOW)
    record, = book.list("sessions")
    raw = book.read(record).split("## What you typed")[1]
    key = "codex:3456-abcdef12"
    assert read_summary(root, key) == {}
    saved = {"key": key, "turns": 2, "title": "A structured session reader", "summary": "Added a session reader. Raw messages remain attached.",
             "tags": ["reader", "rem"], "outcome": "partial", "decisions": [
                 {"time": "09:12", "quote": "Keep the reader simple"},
                 {"time": "09:12", "quote": "Make the reader uncomplicated"},
                 {"time": "09:13", "quote": "Do not change the raw attachment."}],
             "followups": ["Ask Ody about Demo; avoid the melody and Demonstration."],
             "summarised_at": STAMP, "model": "future-model"}
    write_json(summary_path(root, key), saved)
    assert read_summary(root, key) == saved
    assert rewrite_session(root, key) == record
    page = book.read(record)
    assert page.startswith("# A structured session reader\n\n## Summary\n" + saved["summary"])
    assert "- Outcome: partial\n- Tags: reader, rem\n- Started with: Keep the reader simple" in page
    assert "## Decisions\n- “Keep the reader simple” (09:12)" in page
    assert "Make the reader uncomplicated" not in page and "” (09:13)" not in page
    assert "## Follow-ups\n- Ask [Ody](../people/ody.md) about [Demo](../projects/demo.md); avoid the melody and Demonstration." in page
    assert page.split("## What you typed")[1] == raw
    fields = reader_fields(page)
    assert fields["session_title"] == saved["title"] and fields["session_summary"] == saved["summary"]
    assert fields["session_tags"] == saved["tags"] and fields["session_outcome"] == "partial"
    assert fields["session_started_with"] == "Keep the reader simple"
    assert fields["session_turns"] == 2 and "Older turn outside window" not in page
    saved["turns"] = 1
    write_json(summary_path(root, key), saved)
    with maintenance_lock(root):
        rewrite_session(root, key, lock_held=True)
    assert book.read(record).count("## Summary") == 1
    assert book.read(record).split("## What you typed")[1] == raw
    with pytest.raises(RemError, match="not been imported"):
        rewrite_session(root, "codex:missing")


def test_rem_session_reader_fields(notebook):
    root, _, _ = notebook
    transcript(notebook, rows=[codex("Ask  Ody\n  about the reader"), codex("Second message"),
                               codex("Ready.\n  Open the reader.", role="assistant")])
    import_sessions(root, now=NOW)
    book = Notebook(root)
    record, = book.list("sessions")
    fields = reader_fields(book.read(record))
    assert fields == {"session_project": "", "session_date": "2026-10-16", "session_time": "09:12",
                      "session_agent": "Codex", "session_turns": 2, "session_folder": "/work/demo",
                      "session_first": "Ask Ody about the reader", "session_reply": "Ready. Open the reader.",
                      "session_title": "Ask Ody", "session_started_with": "Ask Ody", "session_summary": "",
                      "session_tags": [], "session_outcome": "",
                      "session_artifacts": {"prs": 0, "commits": 0, "files": 0}}
    from connectonion.rem.reader import snapshot
    row = next(r for r in snapshot(root)["records"] if r["path"] == record)
    assert all(row[key] == value for key, value in fields.items())
    no_reply = reader_fields("## What you typed\n### 09:12\n> " + "x" * 400 + "\n## Sources\n")
    assert no_reply["session_first"] == "x" * 300 and no_reply["session_reply"] == ""
    assert reader_fields("## Final reply\n> " + "x" * 400)["session_reply"] == "x" * 300


def test_rem_session_mentions_typed_names_aliases_and_newest_first():
    people = [{"path": "people/ody.md", "title": "周小明", "text": "- Also known as: Ody Zhou [1]; Ody [W2], Unknown"},
              {"path": "people/will.md", "title": "Will", "text": ""},
              {"path": "people/short.md", "title": "Al", "text": ""},
              {"path": "people/held.md", "title": "Ody", "text": "", "needs_review": True}]
    def session(path, typed, reply="", day="2026-10-16", clock="09:12"):
        return {"path": path, "session_date": day, "session_time": clock,
                "text": "## Facts\n- Folder: /Ody\n## What you typed\n### 09:12\n> " + typed
                        + "\n## Final reply\n> " + reply + "\n## Sources\n"}
    sessions = [session("sessions/old.md", "ask Ody", day="2026-10-15"),
                session("sessions/new.md", "请找周小明来看看"),
                session("sessions/alias.md", "ask ODY ZHOU", clock="10:00"),
                session("sessions/tie.md", "ask Ody", clock="10:00"),
                session("sessions/will.md", "ask Will and Al"),
                session("sessions/no.md", "the melody will play", "Ody Zhou and 周小明 and Will"),
                session("sessions/boundary.md", "xOdy Zhou2")]
    assert mentions(people, sessions) == {
        "people/ody.md": ["sessions/alias.md", "sessions/tie.md", "sessions/new.md", "sessions/old.md"],
        "people/will.md": ["sessions/will.md"]}


def test_rem_session_snapshot_mentions_skip_owner_and_review(notebook, monkeypatch):
    root, _, _ = notebook
    book = Notebook(root)
    for person in ("owner", "held", "ody"):
        book.write(f"people/{person}.md", "# Ody\n\n## Facts\n- Also known as: Ody Zhou [1]\n")
    write_json(state_path(root, "map.json"), {"owner": {"record": "people/owner.md"}})
    from connectonion.rem import map as rem_map
    monkeypatch.setattr(rem_map, "needs_review", lambda root: {"people/held.md"})
    transcript(notebook, rows=[codex("ask Ody")])
    import_sessions(root, now=NOW)
    from connectonion.rem.reader import snapshot
    data = snapshot(root)
    people = {r["path"]: r for r in data["records"] if r["category"] == "people"}
    assert people["people/ody.md"]["session_mentions"] == book.list("sessions")
    assert "session_mentions" not in people["people/owner.md"]
    assert "session_mentions" not in people["people/held.md"]


def test_rem_session_redaction_verbatim_labels_and_final_text_only(notebook):
    key = "sk-" + "a" * 30
    reply = codex("[sensitive] " + key + "\n" + "a" * 4000, role="assistant")
    transcript(notebook, rows=[codex("[personal] Keep " + key), reply,
                               {"type": "response_item", "payload": {"type": "function_call", "arguments": "ignored"}}])
    import_sessions(notebook[0], now=NOW)
    book = Notebook(notebook[0])
    page = book.read(book.list("sessions")[0])
    assert key not in page and page.count("[secret-shaped text removed by co rem]") == 3
    assert "[personal] Keep" in page and "[sensitive]" in page
    assert "[truncated by co rem:" in page and "ignored" not in page
    from connectonion.rem.reader import snapshot
    source = next(iter(read_json(state_path(notebook[0], "sessions.json"), {})["sessions"]))
    local = snapshot(notebook[0], local=True)
    assert any(c["excerpt"].startswith("[personal]") for key, c in local["source_context"].items() if key.startswith(source))
    assert not snapshot(notebook[0])["source_context"]


def test_rem_session_claude_final_reply_ignores_sidechains_tools_and_thinking(notebook):
    reply = claude("Visible answer", role="assistant")
    reply["message"]["content"] += [{"type": "thinking", "thinking": "Private reasoning"},
                                      {"type": "tool_use", "input": {"text": "Not an answer"}}]
    transcript(notebook, kind="claude-code", rows=[claude(), reply,
        claude("Sidechain answer", role="assistant", isSidechain=True)])
    import_sessions(notebook[0], now=NOW)
    book = Notebook(notebook[0])
    page = book.read(book.list("sessions")[0])
    assert "> Visible answer" in page
    assert all(text not in page for text in ("Private reasoning", "Not an answer", "Sidechain answer"))


def test_rem_session_window_unreadable_injected_and_notebook_filters(notebook):
    root, _, _ = notebook
    old = transcript(notebook, session="old-file")
    os.utime(old, (NOW.timestamp() - 200 * 86400,) * 2)
    transcript(notebook, session="old-message", rows=[codex(stamp="2025-01-01T00:00:00Z")])
    transcript(notebook, session="harness", rows=[codex("# AGENTS.md instructions\nInjected")])
    transcript(notebook, session="self", cwd=str(root / "notes"))
    bad = transcript(notebook, session="bad")
    bad.write_text("not json\n")
    assert import_sessions(root, now=NOW)["skipped"] == {
        "outside_window": 1, "no_typed_message": 2, "notebook": 1, "unreadable": 1}
    assert import_sessions(root, now=NOW)["unchanged"] == 4


def test_rem_session_expanded_window_reconsiders_skipped_files(notebook):
    transcript(notebook, rows=[codex(stamp="2026-09-01T00:00:00Z")])
    assert import_sessions(notebook[0], days=30, now=NOW)["imported"] == 0
    assert import_sessions(notebook[0], days=180, now=NOW)["imported"] == 1


def test_rem_session_census_uses_date_fact_not_dates_in_quoted_input(notebook):
    transcript(notebook, rows=[codex("Review last: 2030-01-01 and last on 2029-01-01")])
    import_sessions(notebook[0], now=NOW)
    from connectonion.rem.census import counts, pages
    record, = Notebook(notebook[0]).list("sessions")
    assert pages(notebook[0])[record]["last"] == "2026-10-16"
    assert counts(notebook[0])["sessions"] == {"mapped": 1, "written": 1}


def test_rem_session_consent_disabled_and_symlinks(notebook):
    root, directory, subscriptions = notebook
    path = transcript(notebook)
    subscriptions["codex"]["consented"] = False
    assert import_sessions(root, now=NOW, consented_only=True)["imported"] == 0
    subscriptions["codex"]["enabled"] = False
    assert import_sessions(root, now=NOW)["imported"] == 0
    subscriptions["codex"]["enabled"] = True
    (directory / "codex" / "rollout-link.jsonl").symlink_to(path)
    assert import_sessions(root, now=NOW)["imported"] == 1
    assert len(Notebook(root).list("sessions")) == 1


def test_rem_session_long_input_keeps_its_head_and_has_no_reply_section(notebook):
    # A pasted log is not typed words; the page keeps the head, as the source reader does.
    text = "保持简单\n" + "Full typed words " * 400
    transcript(notebook, rows=[codex(text)])
    import_sessions(notebook[0], now=NOW)
    book = Notebook(notebook[0])
    record, = book.list("sessions")
    assert "-session-abcdef12.md" in record
    page = book.read(record)
    assert "> " + text[:3000].replace("\n", "\n> ") in page
    assert "[truncated by co rem:" in page
    assert "## Final reply" not in page


def test_rem_session_title_uses_first_nonempty_line(notebook):
    transcript(notebook, rows=[codex("\n  Build   the reader  \nKeep the body verbatim")])
    import_sessions(notebook[0], now=NOW)
    book = Notebook(notebook[0])
    page = book.read(book.list("sessions")[0])
    assert page.startswith("# Build the reader\n")
    assert "> \n>   Build   the reader  \n> Keep the body verbatim" in page


def test_rem_session_reader_keeps_literal_quotes_and_labels():
    from connectonion.rem.reader import TEMPLATE
    node = shutil.which("node")
    if not node:
        pytest.skip("Node runs the reader's JavaScript")
    template = TEMPLATE.read_text()
    known = re.search(r"function known\(r\) \{.*?(?=\nfunction mappedContact)", template, re.S)[0]
    section = re.search(r"function sectionBody\(r, s\) \{.*?(?=\n// The labels)", template, re.S)[0]
    quote = "# Keep literal headings\n<!-- keep literal comments -->\nidentity unverified\nthe user has [1]\n[personal] Keep labels"
    page = "# Title\n\n## What you typed\n### 09:12\n" + "\n".join("> " + line for line in quote.split("\n")) + "\n"
    script = "\n".join([
        "const KNOWN = new Map(), STAMP = /^Investigation:[^\\n]*$/m;",
        re.search(r"const UNFILLED_LEAD = .*", template)[0],
        "const MECHANICAL = new Set(['facts']), plainLine = x => String(x);",
        "const parseFacts = () => new Map(), skillUsage = () => null;",
        "const el = (tag, attrs, children=[]) => ({tag, ...attrs, children, appendChild(n) { this.children.push(n); }});",
        "const r = " + json.dumps({"category": "sessions", "path": "sessions/a.md", "title": "Title", "text": page}) + ";",
        known, section,
        "console.log(JSON.stringify(sectionBody(r, known(r).kept[0])));",
    ])
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert [child["tag"] for child in rendered["children"]] == ["h3", "blockquote"]
    assert rendered["children"][1]["text"] == quote
    assert rendered["children"][1]["class"] == "session-quote private"


def test_rem_import_sessions_cli_json(notebook):
    from connectonion.cli.main import app
    root, _, _ = notebook
    transcript(notebook)
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "import", "sessions", "--days", "30", "--json"])
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    assert output["ok"] is True and output["data"]["imported"] == 1
    assert "list sessions" in str(output["next"])


@pytest.fixture
def summary_ready(monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("", ""))


def summary_answer(*ids):
    return {"result": json.dumps({"sessions": [dict(
        id=id, title="Build the session reader", summary="Added the reader. The requested work is done.",
        tags=["REM", "Reader UI!", "rem"], outcome="done", decisions=[], followups=[])
        for id in ids]}), "usage": {"input_tokens": 100, "output_tokens": 20, "cost": 0.01}}


def test_rem_session_summarise_batches_persist_and_account(notebook, summary_ready):
    root, _, _ = notebook
    transcript(notebook)
    transcript(notebook, session="second", rows=[codex("Use day headings", stamp="2026-10-16T01:00:00Z")])
    import_sessions(root, now=NOW)
    workspaces, lines = [], []

    def run(workspace, prompt, config, stage):
        assert stage == "abstract" and workspace.parent == state_path(root, "tasks")
        assert workspace.is_dir() and not list(workspace.iterdir())
        with maintenance_lock(root):
            pass  # Model calls must leave the notebook available for other writers.
        assert "Use day headings" in prompt if not workspaces else "Build a simple session reader" in prompt
        workspaces.append(workspace)
        return summary_answer("s1")

    report = summarise_sessions(root, batch=1, run=run, say=lines.append)
    assert {k: report[k] for k in ("summarised", "failed", "batches", "dropped_quotes")} == {
        "summarised": 2, "failed": 0, "batches": 2, "dropped_quotes": 0}
    assert report["usage"] == {"input_tokens": 200, "output_tokens": 40, "cost": 0.02}
    assert len(report["batch_seconds"]) == 2 and report["seconds"] >= 0
    assert len(lines) == 2 and lines[1].startswith("Summarised 1 sessions (batch 2 of 2,")
    assert all(not path.exists() for path in workspaces)
    progress = read_json(state_path(root, "sessions.json"), {})
    for key, record in progress["sessions"].items():
        saved = read_summary(root, key)
        assert saved["turns"] == 1 and saved["summarised_at"] and saved["model"]
        page = Notebook(root).read(record)
        assert "## Summary\nAdded the reader." in page
        assert "- Tags: rem, reader-ui" in page and "- Outcome: done" in page
    assert read_json(state_path(root, "session-tags.json"), {}) == {"rem": 2, "reader-ui": 2}
    record, = service.run_logs(root)
    assert record["phase"] == "sessions-summary" and record["outcome"] == "completed"
    assert record["usage"] == report["usage"] and record["items"] == 2
    assert set(record["changed"]) == set(progress["sessions"].values())
    assert record["runner_attempts"] == 0 and service.status(root)["runner_attempts_today"] == 0
    assert summarise_line(report) == "Summarised 2 of 2 sessions in 2 batches; 0 left for next time; 0 quotes dropped"
    assert summarise_sessions(root, run=lambda *a: pytest.fail("already summarised"))["batches"] == 0


def test_rem_session_summarise_decisions_validate_one_message_and_time(notebook, summary_ready):
    root, _, _ = notebook
    transcript(notebook, rows=[codex("Keep the reader simple"),
        codex("Use day headings", stamp="2026-10-15T22:13:00Z")])
    import_sessions(root, now=NOW)
    answer = summary_answer("s1")
    data = json.loads(answer["result"])
    data["sessions"][0]["decisions"] = [
        {"time": "09:12", "quote": "Make the reader uncomplicated"},
        {"time": "09:12", "quote": "Keep the reader simple"},
        {"time": "09:12", "quote": "Use day headings"}]
    answer["result"] = "```json\n" + json.dumps(data) + "\n```"
    report = summarise_sessions(root, run=lambda *a: answer)
    assert report["dropped_quotes"] == 2 and report["summarised"] == 1
    assert read_summary(root, "codex:3456-abcdef12")["decisions"] == [
        {"time": "09:12", "quote": "Keep the reader simple"}]


def test_rem_session_summarise_drops_empty_decision_spans(notebook, summary_ready):
    root, _, _ = notebook
    transcript(notebook)
    import_sessions(root, now=NOW)
    answer = summary_answer("s1")
    data = json.loads(answer["result"])
    data["sessions"][0]["decisions"] = [{"time": "09:12", "quote": quote}
                                       for quote in ("…", "...", "!!!", "__", "[...](source)")]
    answer["result"] = json.dumps(data)
    report = summarise_sessions(root, run=lambda *a: answer)
    assert report["summarised"] == 1 and report["dropped_quotes"] == 5
    assert read_summary(root, "codex:3456-abcdef12")["decisions"] == []


@pytest.mark.parametrize("reply", ["Here is your summary.", '{"sessions": []}',
    '{"sessions": [{"id": "s1", "title": ""}]}'])
def test_rem_session_summarise_failed_reply_retries(notebook, summary_ready, reply):
    root, _, _ = notebook
    transcript(notebook)
    import_sessions(root, now=NOW)
    report = summarise_sessions(root, run=lambda *a: {"result": reply, "usage": {"input_tokens": 12}})
    assert report["failed"] == 1 and report["summarised"] == 0 and report["batches"] == 1
    assert not summary_path(root, "codex:3456-abcdef12").exists()
    assert not state_path(root, "session-tags.json").exists()
    record, = service.run_logs(root)
    assert record["outcome"] == "failed" and record["usage"] == {"input_tokens": 12}
    assert summarise_sessions(root, run=lambda *a: summary_answer("s1"))["summarised"] == 1


def test_rem_session_summarise_failed_batch_does_not_stop_next(notebook, summary_ready):
    from connectonion.rem.runner import RunFailed
    root, _, _ = notebook
    for number in range(3):
        transcript(notebook, session=str(number))
    import_sessions(root, now=NOW)
    calls = []

    def run(*args):
        calls.append(args)
        if len(calls) == 1:
            raise RunFailed("Provider unavailable", {"input_tokens": 7})
        return summary_answer("s1")

    report = summarise_sessions(root, limit=2, batch=1, run=run)
    assert report["summarised"] == report["failed"] == 1 and report["batches"] == 2
    assert report["usage"]["input_tokens"] == 107
    record, = service.run_logs(root)
    assert record["outcome"] == "partial" and record["items"] == 2 and len(record["changed"]) == 1


def test_rem_session_summarise_turns_grow_and_tags_count_sessions(notebook, summary_ready):
    root, _, _ = notebook
    path = transcript(notebook)
    import_sessions(root, now=NOW)
    summarise_sessions(root, run=lambda *a: summary_answer("s1"))
    with path.open("a") as stream:
        stream.write(json.dumps(codex("Use day headings")) + "\n")
    import_sessions(root, now=NOW)
    assert summarise_sessions(root, run=lambda *a: summary_answer("s1"))["summarised"] == 1
    assert read_summary(root, "codex:3456-abcdef12")["turns"] == 2
    assert read_json(state_path(root, "session-tags.json"), {}) == {"rem": 1, "reader-ui": 1}


def test_rem_session_summarise_not_ready(notebook, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda config: ("Codex is not signed in", "codex login"))
    report = summarise_sessions(notebook[0], run=lambda *a: pytest.fail("not ready"))
    assert report["summarised"] == report["batches"] == 0
    assert report["reason"] == "Codex is not signed in" and report["fix"] == "codex login"
    assert "Codex is not signed in" in summarise_line(report)
    assert service.run_logs(notebook[0]) == []


def test_rem_import_sessions_summarise_cli_json(notebook, monkeypatch):
    from connectonion.cli.main import app
    root, _, _ = notebook
    transcript(notebook)
    calls = []
    report = {"summarised": 1, "failed": 0, "batches": 1, "dropped_quotes": 0}
    monkeypatch.setattr("connectonion.rem.sessions.summarise_sessions",
                        lambda root, **kw: calls.append((root, kw)) or report)
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "import", "sessions", "--summarise", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["summary"] == report
    assert calls == [(root, {"limit": 40})]


def test_rem_import_sessions_summarise_cli_text_and_limit(notebook, monkeypatch):
    from connectonion.cli.main import app
    root, _, _ = notebook
    transcript(notebook)
    report = {"summarised": 2, "failed": 1, "batches": 1, "dropped_quotes": 3}
    calls = []
    monkeypatch.setattr("connectonion.rem.sessions.summarise_sessions",
                        lambda root, **kw: calls.append(kw) or report)
    result = CliRunner().invoke(app, ["rem", "--root", str(root), "import", "sessions", "--summarise", "--limit", "7"])
    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert lines[0].startswith("AI sessions: 1 imported")
    assert lines[1] == "Summarised 2 of 3 sessions in 1 batches; 1 left for next time; 3 quotes dropped"
    assert calls == [{"limit": 7}]


def test_rem_session_summarise_prompt_bounds_and_batch_ids(notebook, summary_ready):
    root, _, _ = notebook
    Notebook(root).stub_project("projects/demo.md", "Demo", paths=["/work/demo"])
    rows = [codex("First message " + "a" * 900)] + [codex("middle " + "b" * 900) for _ in range(20)]
    rows += [codex("Last message " + "z" * 900), codex("Final answer " + "r" * 2000, role="assistant"),
             tool_call("apply_patch", "*** Update File: file.py", custom=True),
             tool_output("[main abcdef0] Build the reader"), tool_call("exec_command", {"cmd": "git push"})]
    transcript(notebook, rows=rows)
    transcript(notebook, session="second")
    import_sessions(root, now=NOW)
    write_json(state_path(root, "session-tags.json"), {f"tag-{i}": i + 1 for i in range(100)})

    def run(workspace, prompt, config, stage):
        instruction, payload = prompt.split("\nSessions:\n")
        vocabulary = instruction.split("Existing tags: ")[1].split(", ")
        assert len(vocabulary) == 80 and vocabulary[0] == "tag-99" and vocabulary[-1] == "tag-20"
        data = json.loads(payload)
        assert [item["id"] for item in data] == ["s1", "s2"]
        item = next(item for item in data if item["typed"].startswith("09:12 First message"))
        assert item["project"] == "Demo" and item["agent"] == "Codex" and item["date"] == "2026-10-16"
        assert len(item["typed"]) == 6000 and "Last message" in item["typed"]
        assert "a" * 800 not in item["typed"] and "z" * 800 not in item["typed"]
        assert len(item["final_reply"]) == 1500
        assert any("abcdef0" in line for line in item["artifacts"])
        assert any("git push" in line for line in item["artifacts"])
        assert all("Files changed" not in line for line in item["artifacts"])
        answer = summary_answer("s2", "s1")  # Output ordering is the model's choice.
        value = json.loads(answer["result"])
        value["sessions"][0].update(outcome="invented", tags=["REM!", " rem ", "reader UI", "a", "b", "c", "d", "e"],
                                    followups=["Ask Ody", 42, "Finish Demo", "Ship reader", "Ignored"])
        answer["result"] = json.dumps(value)
        return answer

    assert summarise_sessions(root, run=run)["summarised"] == 2
    saved = read_summary(root, "codex:second")
    assert saved["outcome"] == "unknown" and saved["tags"] == ["rem", "reader-ui", "a", "b", "c", "d"]
    assert saved["followups"] == ["Ask Ody", "Finish Demo", "Ship reader"]


def test_rem_session_summarise_multilingual_batch_fits_native_argv():
    from connectonion.rem import runner
    from connectonion.rem.sessions import _summary_prompt
    row = {"project": "示例项目", "agent": "Codex", "date": "2026-10-16", "reply": "结果" * 750,
           "messages": [{"time": "09:12", "text": "开头" + "甲" * 798},
                        *[{"time": "09:13", "text": "乙" * 800} for _ in range(10)],
                        {"time": "09:14", "text": "结尾" + "丙" * 798}],
           "artifacts": ["- Commits: `abcdef0` 完成读者界面 (main)", "- Commands: 3 run; notable: `git push`"]}
    prompt = _summary_prompt([row] * 8, {})
    assert len(prompt.encode("utf-8")) <= runner.INLINE_LIMIT
    data = json.loads(prompt.split("\nSessions:\n")[1])
    assert len(data) == 8 and [item["id"] for item in data] == [f"s{i}" for i in range(1, 9)]
    assert all("09:12 开头" in item["typed"] and "09:14 结尾" in item["typed"] for item in data)
    assert all(item["artifacts"] == row["artifacts"] and item["final_reply"] == row["reply"] for item in data)


@pytest.mark.parametrize("reply_ok", [True, False])
def test_rem_session_daily_summarise_preserves_investigation_budget(notebook, summary_ready, monkeypatch, reply_ok):
    from connectonion.rem import daily
    root, _, _ = notebook
    transcript(notebook)
    imported = import_sessions(root, now=NOW)
    set_config(root, ["limits.runner_calls_per_day", "1"])
    Notebook(root).stub_person("people/ody.md", "Ody", ["ody@example.org"])
    monkeypatch.setattr(daily, "unfinished_by_recency", lambda root: [{"path": "people/ody.md"}])
    monkeypatch.setattr(daily, "_clients", lambda sources: {})
    monkeypatch.setattr(daily.quota, "read", lambda *a: {"unknown": "no meter"})
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a: summary_answer("s1") if reply_ok else {
        "result": "prose", "usage": {"input_tokens": 3}})
    investigated, lines = [], []
    result = daily.run_daily(root, maintain=lambda root: {"outcome": "no_change", "sessions": imported},
        investigate_one=lambda *a, **kw: investigated.append(a[1]) or {"changed": [a[1]]}, say=lines.append)
    assert result["maintenance"]["sessions_summary"]["summarised"] == int(reply_ok)
    assert result["outcome"] == "completed" and investigated == ["people/ody.md"]
    assert service.status(root)["runner_attempts_today"] == 1
    assert any(line.startswith("Summarised") and "left for next time" in line for line in lines)
