"""Project pages from the user's own coding messages (#1943, stage 2).

Synthetic Codex rollouts and Claude Code transcripts in the shapes the source
parsers read (tests/unit/test_rem_source.py); never the operator's store.
"""

import json
import os
import re
import stat
import subprocess
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


@pytest.mark.parametrize('lock_held', [False, True])
def test_full_project_refresh_reindexes_older_insertions_before_source_read(world, lock_held):
    from contextlib import nullcontext
    from connectonion.rem import store
    from connectonion.rem.files import maintenance_lock
    from connectonion.rem.reader_model import cited_context
    path = world.codex / 'rollout-index.jsonl'
    codex(path, '/work/tide', [('user', 'Original cited request.', 1)])
    extract(world.root, world.subs, full=True)
    store.refresh(world.root)
    source = stored(world.root, 'projects/tide.md')[0]['source']
    codex(path, '/work/tide', [('user', 'Earlier newly recovered request.', 2)])
    with maintenance_lock(world.root) if lock_held else nullcontext():
        report = extract(world.root, world.subs, full=True, lock_held=lock_held)
    assert cited_context(world.root, [{'text': '- [1] ' + source}])[source]['excerpt'] == 'Original cited request.'
    assert 'sessions' in report['store']['rebuilt']


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


def test_a_small_update_does_not_hide_older_inputs_omitted_from_the_page(world):
    record = "projects/tide.md"
    mark_written(world.root, record, "2026-09-20T00:00:00+00:00", inputs_read=3, inputs_available=5)
    mark_written(world.root, record, "2026-09-21T00:00:00+00:00", inputs_read=1, inputs_available=1)
    assert page_state(world.root, record)["last_page_coverage"] == {
        "inputs_read": 3, "inputs_available": 5, "scope": "queued"}


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


def test_first_write_has_bounded_citable_checkout_evidence_without_secret_files(tmp_path, monkeypatch):
    monkeypatch.setattr(project_material, "project_exclusion", lambda path: "")
    repo = tmp_path / "tide"
    repo.mkdir()
    (repo / "README.md").write_text("# Tide\nWarn surfers when the swell rises.\n"
                                    "Example key sk-live-51Hq8ZzExampleSecretKey0042\n")
    (repo / "pyproject.toml").write_text('[project]\nname = "tide"\nversion = "0.2.0"\n')
    (repo / ".env").write_text("PRIVATE_PASSWORD=never-read-this")
    workflows = repo / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "seo-gate.yml").write_text("name: SEO\njobs:\n  check:\n    steps:\n      - run: node scripts/check-seo.mjs\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "README.md", "pyproject.toml", ".github/workflows/seo-gate.yml"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org",
                    "commit", "-qm", "Add swell warning prototype"], check=True)
    root = tmp_path / "rem"
    prepare(root)
    Notebook(root).stub_project("projects/tide.md", "Tide", [str(repo)])
    source = tmp_path / "codex" / "2026/10/02/rollout-a.jsonl"
    codex(source, str(repo), [("user", "Did the swell warning ship? Check SEO in CI/CD.", 1)])
    extract(root, {"codex": {"kind": "codex", "root": str(tmp_path / "codex"), "enabled": True}})

    items, _ = project_pages.material(root, "projects/tide.md")
    files = [item for item in items if item["role"] == "project-file"]
    assert any(item["origin"].endswith(":pyproject.toml") for item in files)
    assert all(item["source"].startswith("project-source:") for item in files)
    assert any(item["role"] == "readme" and "Warn surfers" in item["text"] for item in items)
    assert all(item["source"] and len(item["text"]) <= 2_100 for item in files)
    assert any(item["role"] == "checkout-state" for item in items)
    assert any(item["role"] == "recent-commits" and "Add swell warning prototype" in item["text"]
               for item in items)
    assert "never-read-this" not in json.dumps(items)
    assert "sk-live" not in json.dumps(items)
    assert any(item.get("origin", "").endswith(":.github/workflows/seo-gate.yml") for item in items)
    assert sum(len(item["text"]) for item in items if item["source"].startswith("project-source:")) <= project_pages.REPOSITORY_EVIDENCE_CHARS
    packet = project_pages._repository_evidence(Notebook(root).read("projects/tide.md"), NOW.isoformat(), NOW.isoformat())
    assert not any(".github/workflows" in item["source"] for item in packet)
    # A moving ref must not relabel newer contents as the already-resolved commit.
    from connectonion.rem import investigate
    git = investigate._git
    original = git(str(repo), "rev-parse", "HEAD")
    (repo / "README.md").write_text("# Tide\nA later unrelated direction.\n")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org",
                    "commit", "-qm", "Change direction later"], check=True)
    later = git(str(repo), "rev-parse", "HEAD")
    subprocess.run(["git", "-C", str(repo), "reset", "--hard", original], check=True, capture_output=True)

    def moving_ref(folder, *args):
        result = git(folder, *args)
        if args == ("rev-parse", "HEAD^{commit}"):
            subprocess.run(["git", "-C", folder, "reset", "--hard", later], check=True, capture_output=True)
        return result

    monkeypatch.setattr(investigate, "_git", moving_ref)
    packet = project_pages._repository_evidence(Notebook(root).read("projects/tide.md"), NOW.isoformat(), NOW.isoformat())
    assert next(item for item in packet if item["role"] == "readme")["source"].endswith(f":{original}:README.md")
    assert "Warn surfers" in next(item for item in packet if item["role"] == "readme")["text"]
    assert "Change direction later" not in next(item for item in packet if item["role"] == "recent-commits")["text"]


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


def test_repository_context_survives_mutable_file_changes_and_rejects_tampering(tmp_path):
    from connectonion.rem.reader_model import cited_context
    from connectonion.rem.files import maintenance_lock
    item = project_pages.repository_snapshots([{"role": "readme", "source": "file:/repo/README.md",
        "text": "# Tide\nWarn surfers.", "timestamp": "2026-10-02T01:00:00Z"}])[0]
    with maintenance_lock(tmp_path):
        assert project_pages.retain_repository_context(tmp_path, [item], set()) == 0
        assert project_pages.retain_repository_context(tmp_path, [item], {item["source"]}) == 1
    later = project_pages.repository_snapshots([{**item, "source": item["origin"], "text": "# Tide\nNew direction."}])[0]
    assert later["source"] != item["source"]
    context = cited_context(tmp_path, [{"text": "- [1] " + item["source"]}])[item["source"]]
    assert context["excerpt"] == "# Tide\nWarn surfers."
    assert context["time"] == "" and context["captured_at"] == item["timestamp"]
    assert context["origin"] == item["origin"]
    path = tmp_path / ".state/project-sources" / (item["source"].split(":")[1] + ".json")
    assert path.stat().st_mode & 0o777 == 0o600
    saved = json.loads(path.read_text())
    path.write_text(json.dumps({**saved, "text": "Wrong body."}))
    assert cited_context(tmp_path, [{"text": "- [1] " + item["source"]}]) == {}


def test_repository_context_shows_a_cited_note_deep_in_a_large_file(tmp_path):
    from connectonion.rem.files import maintenance_lock
    from connectonion.rem.reader_model import cited_context
    original = "Background.\n" * 4_500 + "This dated note records the pending branch.\n"
    item = project_pages.repository_snapshots([{
        "role": "project-file", "snapshot_kind": "git-file", "source": "git:/repo:" + "a" * 40 + ":NOW.md",
        "text": original, "timestamp": "2026-07-24T00:00:00Z"}])[0]
    with maintenance_lock(tmp_path):
        assert project_pages.retain_repository_context(tmp_path, [item], {item["source"]}) == 1
    context = cited_context(tmp_path, [{"text": "- [1] " + item["source"]}])[item["source"]]
    assert "pending branch" in context["excerpt"]
    assert not context["truncated"]


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
    assert page_state(world.root, "projects/tide.md")["last_page_coverage"] == {
        "inputs_read": 1, "inputs_available": 1, "scope": "queued"}
    from connectonion.rem import store
    indexed = store._rows(world.root, "select * from projects where record = ?", ("projects/tide.md",))
    assert indexed[0]["written"] is True
    assert indexed[0]["name"] == "tide"
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


def test_a_project_page_is_also_given_the_start_of_its_readme(tmp_path):
    """#2060: written from the user's typed requests alone, connectonion's page
    described only REM and said "Owner: Unknown" for the owner's own repository."""
    root = tmp_path / "rem"
    prepare(root)
    folder = tmp_path / "work" / "tide"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("# Tide\n\nA swell warning tool for surfers.\n" + "x" * 5000)
    Notebook(root).stub_project("projects/tide.md", "tide", [str(folder)])
    [readme] = project_pages._readme(Notebook(root).read("projects/tide.md"), NOW.isoformat())
    assert readme["source"] == f"file:{folder / 'README.md'}"                # citable by its path
    assert "README.md" in readme["text"] and str(folder) not in readme["text"]
    assert "A swell warning tool for surfers." in readme["text"]
    assert len(readme["text"]) < project_pages.README_CHARS + 200            # the start, not the file
    Notebook(root).stub_project("projects/bare.md", "bare", [str(tmp_path / "work" / "bare")])
    assert project_pages._readme(Notebook(root).read("projects/bare.md"), NOW.isoformat()) == []


def test_the_material_carries_the_readme_beside_the_messages(world, monkeypatch):
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "Add a tide chart.", 1)])
    extract(world.root, world.subs)
    readme = {"role": "readme", "source": "file:/work/tide/README.md", "timestamp": "t", "text": "Tide."}
    monkeypatch.setattr(project_pages, "_readme", lambda page, stamp: [readme])
    items, _ = project_pages.material(world.root, "projects/tide.md")
    packet = next(item for item in items if item["role"] == "readme")
    assert packet["origin"] == readme["source"] and packet["text"] == readme["text"]
    assert sum(1 for item in items if item["role"] == "user") == 1


@pytest.mark.parametrize("accepted", [False, True])
def test_only_an_accepted_project_keeps_its_cited_repository_packet(world, monkeypatch, accepted):
    codex(world.codex / "rollout-packet.jsonl", "/work/tide", [("user", "What does Tide do?", 1)])
    extract(world.root, world.subs)
    item = {"role": "readme", "source": "file:/work/tide/README.md", "timestamp": "2026-10-02T01:00:00Z",
            "text": "A swell warning tool for surfers."}
    monkeypatch.setattr(project_pages, "_repository_evidence", lambda *args, **kwargs: [item])
    source = project_pages.repository_snapshots([item])[0]["source"]
    run = _fake_runner(lambda prompt: _page_citing(source if accepted else "codex:made-up:1"))
    if accepted:
        write_page(world.root, "projects/tide.md", config={"runner": "codex", "model": "default"}, run=run)
        assert project_pages.repository_context(world.root, source)["excerpt"] == item["text"]
    else:
        with pytest.raises(RemError, match="rejected"):
            write_page(world.root, "projects/tide.md", config={"runner": "codex", "model": "default"}, run=run)
        assert not list((world.root / ".state/project-sources").glob("*.json"))


def test_project_items_keep_where_workspace_input_was_supplied():
    item = project_pages._message_items([{"source": "codex:test:1", "timestamp": "2026-10-02T01:00:00Z",
        "tool": "codex", "cwd": "/work/docs-site", "typed_in": "/work/platform", "text": "Add a backend API."}])[0]
    assert item["folder"] == "/work/docs-site" and item["typed_in"] == "/work/platform"


def test_initial_writer_can_search_fixed_implementation_and_declared_cli(tmp_path):
    repo = tmp_path / "invoice"
    (repo / "src/app").mkdir(parents=True)
    (repo / "README.md").write_text("Download PDF at /api/invoice.pdf")
    (repo / "package.json").write_text('{"bin":{"invoice-pdf":"invoice-pdf"}}')
    (repo / "invoice-pdf").write_text("#!/bin/sh\nexec node scripts/render.ts\n")
    (repo / "fixture.json").write_text('{"expected":"example"}')
    (repo / "verify.sh").write_text("#!/bin/sh\nnode scripts/check.ts")
    original = '\n  const href = "/api/invoice.pdf";\n' + "// padding\n" * 1200
    (repo / "src/app/page.tsx").write_text(original)
    (repo / "src/app/link.tsx").symlink_to("page.tsx")
    (repo / ".env").write_text("PASSWORD=must-not-read")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org",
                    "commit", "-qm", "Add invoice"], check=True)
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    (repo / "src/app/page.tsx").write_text("uncommitted different implementation")
    packet = project_pages.repository_snapshots(project_pages._repository_evidence(
        "## Paths\n- " + str(repo) + "\n", NOW.isoformat(), NOW.isoformat()))
    code = [item for item in packet if item.get("snapshot_kind") == "git-file"]
    assert any(item["origin"].endswith(f":{revision}:invoice-pdf") for item in code)
    assert any(item["origin"].endswith(":fixture.json") for item in code)
    assert any(item["origin"].endswith(":verify.sh") for item in code)
    page = next(item for item in code if item["origin"].endswith(":src/app/page.tsx"))
    assert len(page["text"]) > 9000 and "/api/invoice.pdf" in page["text"]
    assert page["text"] == original
    assert "uncommitted" not in page["text"]
    assert not any(item["origin"].endswith(":src/app/link.tsx") for item in code)
    assert "must-not-read" not in json.dumps(packet)
    tree = next(item for item in code if item["origin"].endswith(":tracked-files"))
    assert "src/app/page.tsx" in tree["text"] and "src/app/api" not in tree["text"]
    task = tmp_path / "task"
    task.mkdir()
    prompt = project_pages.prompt(task, packet, task / "candidate.md")
    assert page["text"] not in prompt and "source index" in prompt.lower()
    index = task / "repository/index.md"
    assert index.exists() and "src/app/page.tsx" in index.read_text()
    assert "do not read any other file" not in prompt
    from connectonion.rem.files import maintenance_lock
    with maintenance_lock(tmp_path / "rem"):
        assert project_pages.retain_repository_context(tmp_path / "rem", code, {page["source"]}) == 1
    context = project_pages.repository_context(tmp_path / "rem", page["source"])
    assert context["excerpt"] == page["text"].strip()[:project_pages.REPOSITORY_EXCERPT_CHARS]
    assert context["time"] == "" and context["captured_at"] == NOW.isoformat()


def test_written_project_paths_still_resolve_after_markdown_formatting():
    from connectonion.rem.investigate import project_paths
    page = "## Paths\n- `/work/invoice project` — project repository. [1]\n- /work/other [2][3]\n"
    assert project_paths(page) == ["/work/invoice project", "/work/other"]


def test_large_project_selection_keeps_full_descriptions_entry_and_requested_feature(tmp_path, monkeypatch):
    repo = tmp_path / "large"
    (repo / "pkg/rem").mkdir(parents=True)
    for name in ("a.py", "b.py", "c.py"):
        (repo / name).write_text("print('unrelated')\n")
    (repo / "README.md").write_text("# Large\n" + "logo wall\n" * 400 + "Important product flow below the first prefix.\n")
    (repo / "pyproject.toml").write_text('[project]\nname="large"\n' + "# dependencies\n" * 140
        + '[project.scripts]\nco="pkg.main:cli"\n')
    (repo / "pkg/main.py").write_text("def cli():\n    return 'entry'\n")
    (repo / "pkg/rem/writer.py").write_text("def write():\n    return 'requested'\n")
    (repo / "docs").mkdir()
    (repo / "docs/lock.md").write_text("Later mention, supporting documentation.\n")
    (repo / "tests").mkdir()
    (repo / "tests/test_lock.py").write_text("def test_lock():\n    assert True\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org",
                    "commit", "-qm", "Large source index"], check=True)
    monkeypatch.setattr(project_pages, "IMPLEMENTATION_FILES", 4)
    items = project_pages._repository_evidence("## Paths\n- " + str(repo) + "\n", NOW.isoformat(), NOW.isoformat(),
                                              requests="Check REM, then lock.")
    indexed = [item for item in items if item.get("snapshot_kind") == "git-file" and item["subject"] != "tracked-files"]
    assert {item["subject"] for item in indexed} == {"README.md", "pyproject.toml", "pkg/main.py", "pkg/rem/writer.py"}
    assert "Important product flow" in next(item["text"] for item in indexed if item["subject"] == "README.md")
    assert '[project.scripts]' in next(item["text"] for item in indexed if item["subject"] == "pyproject.toml")


def test_initial_source_index_states_omissions_and_preserves_complete_tree(tmp_path, monkeypatch):
    repo = tmp_path / "bounded"
    repo.mkdir()
    (repo / "a.py").write_text("# " + "x" * 300)
    (repo / "b.py").write_text("print('second')\n")
    (repo / "package-lock.json").write_text('{"ignored":"dependency metadata"}')
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org",
                    "commit", "-qm", "Bounded sources"], check=True)
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    monkeypatch.setattr(project_pages, "IMPLEMENTATION_FILES", 1)
    # A deliberately small byte cap for the selected body; tree uses the real retention limit.
    monkeypatch.setattr(project_pages, "FILE_SNAPSHOT_CHARS", 256)
    items = project_pages._implementation_evidence(str(repo), revision, NOW.isoformat())
    assert len(items) == 1  # first selected file is too large, rather than supplied partially
    assert "0 of 2 eligible" in items[0]["text"]
    assert "[truncated]" in items[0]["text"]  # this deliberately tiny cap also bounds the tree
    monkeypatch.setattr(project_pages, "FILE_SNAPSHOT_CHARS", 1_000_000)
    items = project_pages._implementation_evidence(str(repo), revision, NOW.isoformat())
    assert len(items) == 2 and "a.py" in items[0]["text"] and "b.py" in items[0]["text"]
    assert "1 of 2 eligible" in items[0]["text"] and "omitted" in items[0]["text"]


def test_the_busiest_project_comes_first_and_recency_only_breaks_ties(world):
    """#2079: by recency alone a fresh init wrote the owner's private journal
    before LayeredVisions (28 sessions) and browser (17)."""
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide/docs", [("user", "one docs note", 1)])
    codex(world.codex / "2026/08/01/rollout-c.jsonl", "/work/old-bot",
          [("user", f"bot work {n}", 30 + n) for n in range(6)])
    extract(world.root, world.subs)
    assert [r["record"] for r in queue(world.root, now=NOW)][:2] == ["projects/old-bot.md", "projects/tide-docs.md"]


def test_a_private_folder_is_mapped_but_never_queued(world):
    """#2079: the first run wrote up a diary repository's requests about family names."""
    world.notebook.stub_project("projects/journal.md", "journal", ["/Users/me/journal"])
    codex(world.codex / "2026/09/29/rollout-j.jsonl", "/Users/me/journal",
          [("user", f"diary entry {n}", 1) for n in range(9)])
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "tide work", 2)])
    extract(world.root, world.subs)
    assert "projects/journal.md" not in [r["record"] for r in queue(world.root, now=NOW)]
    assert project_pages.private("projects/journal.md", world.notebook.read("projects/journal.md"))
    assert not project_pages.private("projects/tide.md", world.notebook.read("projects/tide.md"))
    world.notebook.stub_project("projects/beta.md", "beta", ["/private/var/folders/x/beta"])
    assert not project_pages.private("projects/beta.md", world.notebook.read("projects/beta.md"))  # macOS temp
    from connectonion.rem.queue import order
    assert "projects/journal.md" not in [r["path"] for r in order(world.root, "projects")]

def test_a_project_turn_that_writes_no_candidate_gets_one_more_turn(world):
    """iter9 (2026-10-01): docs-site was lost to 'did not write candidate.md'
    after the investigation path had learned to ask again; project pages run
    their own turn and had not."""
    codex(world.codex / "2026/09/20/rollout-a.jsonl", "/work/tide", [("user", "Tide should warn surfers.", 1)])
    extract(world.root, world.subs)
    source = stored(world.root, "projects/tide.md")[0]["source"]
    writes = _fake_runner(lambda prompt: _page_citing(source))
    calls = []

    def run(workdir, prompt, config, stage):
        calls.append(prompt)
        if len(calls) == 1:
            return {"outcome": "natural", "result": "cannot write there", "usage": {"input_tokens": 100}}
        return writes(workdir, prompt, config, stage)

    write_page(world.root, "projects/tide.md", config={"runner": "codex", "model": "default"}, run=run)
    assert len(calls) == 2 and "writable" in calls[1]
    assert "A swell warning tool for surfers. [1]" in world.notebook.read("projects/tide.md")


def test_full_file_retention_does_not_expand_packet_bound_or_ignore_private_tail(tmp_path):
    from connectonion.rem.files import maintenance_lock
    items = project_pages.repository_snapshots([
        {'role': 'readme', 'source': 'file:/repo/README.md', 'text': 'a' * 9001},
        {'role': 'project-file', 'source': 'file:/repo/api.ts', 'snapshot_kind': 'local-file',
         'text': 'a' * 12000 + '\nA private plan [personal]'},
    ])
    with maintenance_lock(tmp_path):
        assert project_pages.retain_repository_context(tmp_path, items, {i['source'] for i in items}) == 0
    assert not list((tmp_path / '.state/project-sources').glob('*.json'))
