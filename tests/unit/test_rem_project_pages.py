"""Project pages from the user's own coding messages (#1943, stage 2).

Synthetic Codex rollouts and Claude Code transcripts in the shapes the source
parsers read (tests/unit/test_rem_source.py); never the operator's store.
"""

import json
import os
import re
import stat
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from connectonion.rem import project_material, project_pages
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError
from connectonion.rem.project_material import extract, mark_written, page_state, stored
from connectonion.rem.project_pages import PROMPT_CHARS, queue, write_page, write_pages

NOW = datetime.now(timezone.utc)


def ago(days: float) -> str:
    return (NOW - timedelta(days=days)).isoformat().replace("+00:00", "Z")


def codex(path: Path, cwd: str, rows, *, session="", originator="codex_cli_rs"):
    """rows: (role, text, days_ago[, extra payload keys])."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "session_meta", "payload": {"id": session or path.stem, "cwd": cwd, "originator": originator}}]
    for role, text, days, *extra in rows:
        payload = {"type": "message", "role": role, "content": [{"type": "input_text", "text": text}]}
        payload.update(extra[0] if extra else {})
        lines.append({"timestamp": ago(days), "type": "response_item", "payload": payload})
    # A second call appends to the same session, as a running session does.
    if path.exists():
        lines = lines[1:]
    with path.open("a") as handle:
        handle.write("".join(json.dumps(row) + "\n" for row in lines))


def claude(path: Path, cwd: str, rows, *, session="sess-1"):
    """rows: (type, content, days_ago, extra)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"type": "file-history-snapshot", "messageId": "m0", "snapshot": {}})]
    for index, (kind, content, days, extra) in enumerate(rows):
        lines.append(json.dumps({"type": kind, "timestamp": ago(days), "cwd": cwd, "sessionId": session,
                                 "uuid": f"u{index}", "userType": "external",
                                 "message": {"role": kind, "content": content}, **extra}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "rem"
    prepare(root)
    notebook = Notebook(root)
    notebook.stub_project("projects/tide.md", "tide", ["/work/tide"], sessions=2, first_seen="2026-09-01",
                          last_seen="2026-09-29")
    notebook.stub_project("projects/tide-docs.md", "tide-docs", ["/work/tide/docs"])
    notebook.stub_project("projects/old-bot.md", "old-bot", ["/work/old-bot"])
    codex_root, claude_root = tmp_path / "codex", tmp_path / "claude"
    subs = {"codex": {"kind": "codex", "root": str(codex_root), "enabled": True},
            "claude-code": {"kind": "claude-code", "root": str(claude_root), "enabled": True}}
    return types.SimpleNamespace(root=root, notebook=notebook, codex=codex_root, claude=claude_root, subs=subs)


def test_only_what_the_user_typed_is_kept_and_filed_under_its_page(world):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [
        ("user", "Tide should warn surfers when the swell passes 2m.", 3),
        ("assistant", "Added the swell check.", 3),
        ("user", "<environment_context>cwd /work/tide</environment_context>", 3),
        ("user", "injected", 3, {"id": "x", "internal_chat_message_metadata_passthrough": {}}),
    ])
    claude(world.claude / "-work-tide-docs/s.jsonl", "/work/tide/docs/site", [
        ("user", "Write the docs landing page in plain English.", 2, {}),
        ("user", [{"type": "tool_result", "tool_use_id": "t", "content": "42 passed"}], 2, {}),
        ("user", "You are one finder angle in a review", 2, {"isSidechain": True}),
        ("assistant", [{"type": "text", "text": "Done."}], 2, {}),
    ])
    codex(world.codex / "2026/08/01/rollout-w.jsonl", "/work/nowhere", [("user", "an old folder with no page", 40)])
    codex(world.codex / "2026/09/21/rollout-t.jsonl", "/tmp/scratch", [("user", "scratch", 1)])
    codex(world.codex / "2026/09/21/rollout-o.jsonl", "/work/tide", [("user", "notebook run", 1)],
          originator="co_rem")

    report = extract(world.root, world.subs)

    assert [m["text"] for m in stored(world.root, "projects/tide.md")] == [
        "Tide should warn surfers when the swell passes 2m."]
    # The deepest listed folder wins: /work/tide/docs/site belongs to tide-docs, not tide.
    assert [m["text"] for m in stored(world.root, "projects/tide-docs.md")] == [
        "Write the docs landing page in plain English."]
    assert stored(world.root, "projects/old-bot.md") == []
    assert [row["path"] for row in report["unmapped"]] == ["/work/nowhere"]
    assert report["excluded"] == {"temporary execution directory": 1}
    material = (world.root / ".state/projects/tide/messages.md").read_text()
    assert material.startswith("### codex:rollout-a:") and "Added the swell check" not in material
    # The report is counts and paths, never what was said.
    assert "swell" not in json.dumps(report)


def test_the_material_is_private(world):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "private words", 1)])
    extract(world.root, world.subs)
    folder = world.root / ".state/projects/tide"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE((world.root / ".state/projects").stat().st_mode) == 0o700
    for name in ("messages.md", "messages.jsonl", "state.json"):
        assert stat.S_IMODE((folder / name).stat().st_mode) == 0o600, name


def test_a_key_shaped_string_never_reaches_the_disk(world):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide",
          [("user", "use sk-live-51Hq8ZzExampleSecretKey0042 for the test account", 1)])
    extract(world.root, world.subs)
    for name in ("messages.md", "messages.jsonl"):
        text = (world.root / ".state/projects/tide" / name).read_text()
        assert "sk-live" not in text and project_material.REDACTED in text


def test_a_later_extraction_reads_only_what_is_new_and_counts_nothing_twice(world, monkeypatch):
    file = world.codex / "2026/09/20/rollout-a.jsonl"
    codex(file, "/work/tide", [("user", "first", 2)])
    extract(world.root, world.subs)
    codex(file, "/work/tide", [("user", "second", 0.01)])
    report = extract(world.root, world.subs)
    assert [m["text"] for m in stored(world.root, "projects/tide.md")] == ["first", "second"]
    assert next(p for p in report["pages"] if p["record"] == "projects/tide.md")["added"] == 1
    # The second pass started at the first one's time, less the overlap -- not 180 days back.
    first_pass = datetime.fromisoformat(report["since"])
    assert NOW - first_pass < timedelta(hours=2)
    # A re-read of the same lines adds nothing.
    assert next(p for p in extract(world.root, world.subs, full=True)["pages"]
                if p["record"] == "projects/tide.md")["messages"] == 2


def test_since_limits_the_read_to_messages_after_it(world):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "old", 30), ("user", "new", 1)])
    extract(world.root, world.subs, since=NOW - timedelta(days=7))
    assert [m["text"] for m in stored(world.root, "projects/tide.md")] == ["new"]


def test_stored_material_keeps_the_newest_within_its_cap(world, monkeypatch):
    monkeypatch.setattr(project_material, "MAX_STORED_CHARS", 25)
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide",
          [("user", "a" * 10, 3), ("user", "b" * 10, 2), ("user", "c" * 10, 1)])
    extract(world.root, world.subs)
    assert [m["text"][0] for m in stored(world.root, "projects/tide.md")] == ["b", "c"]
    assert page_state(world.root, "projects/tide.md")["dropped_older"] == 1


def test_recent_projects_come_first_then_older_ones_newest_first(world):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "tide work", 5)])
    codex(world.codex / "2026/09/20/rollout-b.jsonl", "/work/tide/docs", [("user", "docs work", 1)])
    codex(world.codex / "2026/08/01/rollout-c.jsonl", "/work/old-bot", [("user", "bot work", 40)])
    extract(world.root, world.subs)
    rows = queue(world.root, now=NOW)
    assert [(r["record"], r["recent"], r["mode"]) for r in rows] == [
        ("projects/tide-docs.md", True, "first"), ("projects/tide.md", True, "first"),
        ("projects/old-bot.md", False, "first")]
    assert [r["record"] for r in queue(world.root, recent_days=60, now=NOW)][-1] == "projects/old-bot.md"


def test_a_written_page_waits_for_new_messages_and_then_gets_only_those(world):
    file = world.codex / "2026/09/20/rollout-a.jsonl"
    codex(file, "/work/tide", [("user", "first", 2)])
    extract(world.root, world.subs)
    mark_written(world.root, "projects/tide.md", stored(world.root, "projects/tide.md")[-1]["timestamp"])
    assert "projects/tide.md" not in [r["record"] for r in queue(world.root)]
    codex(file, "/work/tide", [("user", "second", 0.01)])
    extract(world.root, world.subs)
    row = next(r for r in queue(world.root) if r["record"] == "projects/tide.md")
    assert (row["mode"], row["new_messages"]) == ("update", 1)
    items, _ = project_pages.material(world.root, "projects/tide.md")
    assert [i["text"] for i in items if i["role"] == "user"] == ["second"]
    assert "This is an update" in items[1]["text"]


def test_one_call_carries_the_newest_messages_that_fit_and_says_what_it_left_out(world, monkeypatch):
    monkeypatch.setattr(project_pages, "PROMPT_CHARS", 25)
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide",
          [("user", "a" * 10, 3), ("user", "b" * 10, 2), ("user", "c" * 10, 1)])
    extract(world.root, world.subs)
    items, through = project_pages.material(world.root, "projects/tide.md")
    assert [i["text"][0] for i in items if i["role"] == "user"] == ["b", "c"]
    assert "1 older messages did not fit" in items[1]["text"]
    assert through == stored(world.root, "projects/tide.md")[-1]["timestamp"]
    assert PROMPT_CHARS == 60_000  # the documented cap


def _fake_runner(page_from):
    """A runner that writes the candidate the prompt names, as co ai would."""
    calls = []

    def run(workdir, prompt, config, stage):
        calls.append(prompt)
        candidate = Path(re.search(r"NEW file (\S+candidate\.md)", prompt)[1])
        candidate.write_text(page_from(prompt))
        return {"outcome": "natural", "result": "read 1 message", "usage": {"input_tokens": 100}}
    run.calls = calls
    return run


def _page_citing(source):
    page = Notebook.__new__(Notebook)  # only for PROJECT_SECTIONS
    lines = ["# tide"]
    for section in page.PROJECT_SECTIONS:
        lines += ["", f"## {section}"]
        if section == "What it is":
            lines.append("A swell warning tool for surfers. [1]")
        elif section == "Paths":
            lines += ["- /work/tide", "- Sessions: 2", "- First seen: 2026-09-01", "- Last seen: 2026-09-29"]
        else:
            lines.append("- Unknown")
    lines += ["", "## Sources", f"- [1] {source} — 2026-09-28", ""]
    return "\n".join(lines)


def test_a_page_is_written_once_from_the_material_and_the_status_line_says_so(world):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide",
          [("user", "Tide should warn surfers. key sk-live-51Hq8ZzExampleSecretKey0042", 1)])
    extract(world.root, world.subs)
    source = stored(world.root, "projects/tide.md")[0]["source"]
    run = _fake_runner(lambda prompt: _page_citing(source))
    out = write_page(world.root, "projects/tide.md", config={"runner": "codex", "model": "default"}, run=run)
    page = world.notebook.read("projects/tide.md")
    assert "A swell warning tool for surfers. [1]" in page
    assert re.search(r"^Investigation: .*written \d{4}-\d\d-\d\d \(own messages: codex\)$", page, re.M)
    assert page_state(world.root, "projects/tide.md")["written_through"] == out["through"]
    assert queue(world.root) == [] or "projects/tide.md" not in [r["record"] for r in queue(world.root)]
    prompt = run.calls[0]
    assert "# A project page from the user's own messages" in prompt and "# A project's page" in prompt
    assert "sk-live" not in prompt and "Tide should warn surfers" in prompt
    # The run's own prompt lands in a session file too; it must never be read
    # back as something the user typed.
    from connectonion.rem.source import INJECTED_BLOCK
    assert INJECTED_BLOCK.match(prompt) and not prompt.startswith("/")


def test_a_refused_page_leaves_its_messages_pending(world):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "Tide warns surfers.", 1)])
    extract(world.root, world.subs)
    before = world.notebook.read("projects/tide.md")
    run = _fake_runner(lambda prompt: _page_citing("codex:made-up:1"))
    with pytest.raises(RemError, match="rejected"):
        write_page(world.root, "projects/tide.md", config={"runner": "codex", "model": "default"}, run=run)
    assert world.notebook.read("projects/tide.md") == before
    assert page_state(world.root, "projects/tide.md")["written_through"] == ""
    # #2026: refused for this material, it waits for newer messages instead of
    # being retried with the same ones on every sync (~260k tokens, 0 changes).
    assert "projects/tide.md" not in [r["record"] for r in queue(world.root)]
    assert not list((world.root / ".state/tasks").glob("projects-*/material.*"))   # #2029
    codex(world.codex / "2026/09/21/rollout-b.jsonl", "/work/tide", [("user", "Tide now warns by SMS.", 0)])
    extract(world.root, world.subs)
    assert "projects/tide.md" in [r["record"] for r in queue(world.root)]


def test_the_page_s_size_and_the_limit_are_said_before_the_turn(tmp_path):
    """#2026: the 20k limit lived only in the review, so a 24.6k page was written
    at full length and refused."""
    from connectonion.rem.project_pages import prompt

    small = prompt(tmp_path, [{"role": "page", "text": "# t"}], tmp_path / "candidate.md", 4_000)
    large = prompt(tmp_path, [{"role": "page", "text": "# t"}], tmp_path / "candidate.md", 24_586)
    assert "must stay under 20,000 characters" in small
    assert "The page is 24,586 characters" in large and "fold the oldest History" in large


def test_write_pages_takes_a_portion_in_order_and_one_failure_does_not_stop_the_rest(world):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "tide", 5)])
    codex(world.codex / "2026/09/20/rollout-b.jsonl", "/work/tide/docs", [("user", "docs", 1)])
    codex(world.codex / "2026/08/01/rollout-c.jsonl", "/work/old-bot", [("user", "bot", 40)])
    extract(world.root, world.subs)
    seen = []

    def write(record):
        seen.append(record)
        if record == "projects/tide-docs.md":
            raise RemError("Candidate rejected, kept at x: Missing citation")
    result = write_pages(world.root, limit=2, write=write)
    assert seen == ["projects/tide-docs.md", "projects/tide.md"]
    assert [row["outcome"] for row in result["pages"]] == ["refused", "accepted"]
    assert write_pages(world.root, limit=1, write=seen.append, gate=lambda: "budget spent") == \
        {"pages": [], "left": 3, "stopped": "budget spent"}


def test_the_skill_has_valid_frontmatter_and_is_not_composed_into_other_stages():
    from connectonion.skills_catalog import useful_skills_dir
    from connectonion.rem.runner import instructions
    text = (useful_skills_dir() / "rem-project-sessions/SKILL.md").read_text()
    front = yaml.safe_load(text.split("---\n")[1])
    assert front["name"] == "rem-project-sessions" and front["description"].strip()
    # Named outside rem-page-*: those are composed into every page-writing stage.
    for stage in ("init", "maintain", "investigate"):
        assert "# A project page from the user's own messages" not in instructions(stage)
    assert project_pages.instructions().startswith(text)


def test_projects_shows_the_order_and_the_cost_and_spends_nothing(world, monkeypatch):
    from typer.testing import CliRunner

    from connectonion.cli.main import app
    home = Path(os.environ["HOME"])
    codex(home / ".codex/sessions/2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "tide", 1)])
    monkeypatch.setattr("connectonion.rem.runner.run_task", lambda *a, **k: pytest.fail("model called"))
    result = CliRunner().invoke(app, ["rem", "--root", str(world.root), "projects"])
    assert result.exit_code == 0, result.output
    assert "projects/tide.md  (last active" in result.stdout and "first write" in result.stdout
    assert "Cost: 1 model call(s)" in result.stdout and "Nothing was spent." in result.stdout
    assert f"Next: co rem --root {world.root} projects write" in result.stdout


def _two_active_projects(world):
    home = Path(os.environ["HOME"])
    codex(home / ".codex/sessions/2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "tide", 1)])
    codex(home / ".codex/sessions/2026/09/20/rollout-b.jsonl", "/work/old-bot", [("user", "bot", 2)])


def test_projects_write_ends_with_a_readable_summary_not_a_yaml_dump(world, monkeypatch):
    """#2008: 1.9.0a5 ended `projects write` with `pages:` / `outcome: accepted` YAML."""
    from typer.testing import CliRunner

    from connectonion.cli.main import app
    _two_active_projects(world)
    monkeypatch.setattr("connectonion.rem.project_pages.write_page",
                        lambda root, record, **kw: {"record": record, "changed": [record]})
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter in tests"})
    result = CliRunner().invoke(app, ["rem", "--root", str(world.root), "projects", "write"])
    assert result.exit_code == 0, result.output
    assert "Wrote 2 project pages of 2." in result.stdout
    assert "  projects/tide.md: written" in result.stdout
    assert "outcome:" not in result.stdout and "pages:" not in result.stdout
    assert "billed input tokens" in result.output and "(1 new message, first write)" not in result.output


def test_ctrl_c_in_projects_write_names_what_was_written_and_the_next_command(world, monkeypatch):
    from typer.testing import CliRunner

    from connectonion.cli.main import app
    _two_active_projects(world)
    done = []

    def write(root, record, **kw):
        if done:
            raise KeyboardInterrupt
        done.append(record)
        return {"record": record, "changed": [record]}

    monkeypatch.setattr("connectonion.rem.project_pages.write_page", write)
    monkeypatch.setattr("connectonion.rem.quota.read", lambda config: {"unknown": "no meter in tests"})
    result = CliRunner().invoke(app, ["rem", "--root", str(world.root), "projects", "write"])
    assert result.exit_code == 130
    assert f"Stopped: 1 page written before the stop ({done[0]}), and kept." in result.stdout
    assert f"Next: co rem --root {world.root} projects write" in result.stdout


def test_one_new_message_is_singular(world):
    from connectonion.cli.commands.rem_projects import _order_lines
    row = {"record": "projects/tide.md", "last_activity": "2026-09-29T00:00:00Z", "new_messages": 1,
           "mode": "first", "left_out": 0}
    assert _order_lines([row]) == ["  projects/tide.md  (last active 2026-09-29, 1 message, first write)"]
