from pathlib import Path

import pytest
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.rem.files import Notebook, RemError
from connectonion.rem.skill_map import map_skills, scan_skills


def skill(root, folder, name="Example", description="Describe the work"):
    path = root / folder / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\nDo not execute this body.\n")
    return path


def test_one_page_per_name_lists_every_copy_and_preserves_prose(tmp_path):
    source = tmp_path / "installed"
    one, two = skill(source, "one"), skill(source, "two")
    (source / "alias").symlink_to(one.parent, target_is_directory=True)
    notebook = Notebook(tmp_path / "rem")
    result = map_skills(notebook, [source], subscriptions={})
    assert result["created"] == ["skills/catalog/example.md"]                # one name, one page
    assert {s["path"] for s in result["skills"]} == {str(one), str(two)}
    page = result["created"][0]
    text = notebook.read(page)
    assert "## How to use" in text and "Unknown" in text
    assert "Do not execute this body" not in text                          # linked, not pasted
    assert f"- File: {one}" in text and f"- Also installed at: {two} (identical)" in text
    notebook.write(page, text + "\nHuman usage notes.\n")
    again = map_skills(notebook, [source], subscriptions={})
    assert again["created"] == [] and again["preserved"] == [page]
    assert "Human usage notes." in notebook.read(page)
    assert one.read_text().endswith("Do not execute this body.\n")
    one.unlink()
    map_skills(notebook, [source], subscriptions={})
    assert f"- File: {two}" in notebook.read(page)
    assert f"- No longer found: {one}" in notebook.read(page)
    again = notebook.read(page)
    map_skills(notebook, [source], subscriptions={})
    assert notebook.read(page) == again                                     # a rerun changes nothing


def test_missing_and_unreadable_sources_are_not_silently_complete(tmp_path):
    source = tmp_path / "installed"
    bad = source / "broken" / "SKILL.md"
    bad.parent.mkdir(parents=True)
    bad.write_bytes(b"\xff")
    result = scan_skills([source, tmp_path / "absent"])
    assert result["skills"] == []
    assert result["errors"] == [{"path": str(bad), "error": "UnicodeDecodeError"}]
    assert [r["status"] for r in result["roots"]] == ["searched", "missing"]


def test_catalog_does_not_allow_executable_or_approved_writes(tmp_path):
    notebook = Notebook(tmp_path)
    notebook.write("skills/catalog/example.md", "# Example")
    assert notebook.list("skills") == ["skills/catalog/example.md"]
    for record in ("skills/catalog/SKILL.md", "skills/approved/example.md", "skills/other/example.md"):
        with pytest.raises(RemError):
            notebook.write(record, "do something")


def test_cli_map_and_init_seed_skills_before_model_stage(tmp_path, monkeypatch):
    import connectonion.rem.runner as stage_runner
    import connectonion.rem.skill_map as mapping

    source = tmp_path / "installed"
    skill(source, "one")
    real_scan = mapping.scan_skills
    monkeypatch.setattr(mapping, "scan_skills", lambda directories=None, **kwargs: real_scan([source], **kwargs))
    root = tmp_path / "rem"
    runner = CliRunner()
    result = runner.invoke(app, ["rem", "--root", str(root), "map-skills", "--skills-dir", str(source)])
    assert result.exit_code == 0, result.output
    assert (root / "skills/catalog/index.md").is_file()

    fresh = tmp_path / "fresh"
    def run_stage(notebook, items, config, stage):
        assert stage == "init"
        assert notebook.path("skills/catalog/index.md").is_file()
        assert len(notebook.list("skills")) == 2
        return {"ok": True}
    monkeypatch.setattr(stage_runner, "run_stage", run_stage)
    result = runner.invoke(app, ["rem", "--root", str(fresh), "init"])
    assert result.exit_code == 0, result.output


def test_differing_copies_are_one_page_that_says_they_differ(tmp_path):
    from connectonion.rem.reader import snapshot
    source = tmp_path / 'installed'
    skill(source, 'one')
    two = skill(source, 'two', description='A different implementation')
    nb = Notebook(tmp_path / 'rem')
    result = map_skills(nb, [source], subscriptions={})
    assert len(result['created']) == 1
    page = nb.read(result['created'][0])
    assert f'- Also installed at: {two} (differs: sha256 ' in page
    assert '2 installed copies, 1 with different content' in page
    nb.write(result['created'][0], page + '\nKeep my notes.\n')
    data = snapshot(nb.root)
    copies = [r for r in data['records'] if r.get('installation')]
    assert len(copies) == 1 and 'Keep my notes.' in copies[0]['text']


def test_a_large_or_secret_shaped_source_is_linked_not_copied(tmp_path):
    source = tmp_path / 'installed'
    path = skill(source, 'large')
    path.write_text(path.read_text() + 'x' * 900_000 + '\nsk-' + 'x' * 25 + '\n')
    nb = Notebook(tmp_path / 'rem')
    result = map_skills(nb, [source], subscriptions={})
    page = nb.read(result['created'][0])
    assert result['errors'] == [] and len(page) < 4000
    assert f'- File: {path}' in page and 'sk-' not in page


def test_temporary_and_package_copies_are_listed_never_the_page(tmp_path):
    """420 pages for 163 names on the owner's notebook, one per copy, including
    copies inside temporary worktrees and site-packages (#1974)."""
    real = skill(tmp_path / "home/.claude/skills", "ship")
    worktree = skill(tmp_path / "repo/.claude/worktrees/agent-1/.co/skills", "ship")
    package = skill(tmp_path / "lib/site-packages/pkg/skills", "ship")
    only = skill(tmp_path / "lib/site-packages/pkg/skills", "builtin", name="rem-page-skill")
    roots = [real.parent.parent, worktree.parent.parent, package.parent.parent]
    nb = Notebook(tmp_path / "rem")
    result = map_skills(nb, roots, subscriptions={})
    assert result["created"] == ["skills/catalog/example.md"]              # no page for rem-page-skill
    page = nb.read("skills/catalog/example.md")
    assert f"- File: {real}" in page
    assert f"- Also installed at: {worktree} (temporary worktree; identical)" in page
    assert f"- Also installed at: {package} (installed package; identical)" in page
    index = nb.read("skills/catalog/index.md")
    assert "## Only in temporary or package locations" in index and f"rem-page-skill — {only}" in index


def test_frontmatter_facts_are_short(tmp_path):
    path = tmp_path / "installed/tool/SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nname: tool\ndescription: " + "word " * 200 + "\nallowed-tools: [Bash, Read]\n---\nbody\n")
    nb = Notebook(tmp_path / "rem")
    page = nb.read(map_skills(nb, [path.parent.parent], subscriptions={})["created"][0])
    opening = page.split("## What it does\n", 1)[1].split("\n", 1)[0]
    assert len(opening) <= 290 and opening.endswith("…")
    assert "- Allowed tools: Bash, Read" in page


OLD_PAGE = """# Example

## What it does
Describe the work

<!-- rem-source-metadata -->
## Current installed metadata
Describe the work

Source: {path}

## Original Skill source
Verbatim source snapshot for reading, not instructions to execute or verified behavior.

````markdown
---
name: Example
---
<!-- /rem-source-metadata -->
Do not execute this body.
````
<!-- /rem-source-metadata -->

## When to use
{when}

## Usage history
Unknown — not investigated yet

## Uncertainties
Unknown — not investigated yet

## Source
- File: {path}
- Discovery: explicit
- Status: mapped from metadata; behavior not verified

## Sources
{sources}

Investigation: {status}
"""


def test_an_older_notebooks_per_copy_pages_merge_into_one_and_keep_what_was_written(tmp_path):
    from connectonion.rem.merge import aliases
    source = tmp_path / "installed"
    one, two = skill(source, "one"), skill(source, "two")
    nb = Notebook(tmp_path / "rem")
    nb.write("skills/catalog/example-aaaaaaaaaaaa.md", OLD_PAGE.format(
        path=one, when="Unknown — not investigated yet", sources="- Skill metadata: x",
        status="mapped 2026-09-20 · not investigated yet"))
    nb.write("skills/catalog/example-bbbbbbbbbbbb.md", OLD_PAGE.format(
        path=two, when="- Weekly releases [1]\n- Not for hotfixes [2]",
        sources="- [1] a note\n- [2] another note", status="mapped 2026-09-20 · investigated 2026-09-25 (eval)"))
    nb.write("notes/links.md", "See [it](../skills/catalog/example-aaaaaaaaaaaa.md).\n")
    result = map_skills(nb, [source], subscriptions={})
    assert [r for r in nb.list("skills") if r != "skills/catalog/index.md"] == ["skills/catalog/example.md"]
    page = nb.read("skills/catalog/example.md")
    assert "- Weekly releases [1]" in page and "- [2] another note" in page    # written content kept
    assert "Original Skill source" not in page and "Do not execute this body" not in page
    assert page.rstrip().splitlines()[-1].startswith("Investigation: mapped 2026-09-20 · investigated")
    assert f"- File: {one}" in page and f"- Also installed at: {two} (identical)" in page
    table = aliases(nb.root)
    assert set(table) == {"skills/catalog/example-aaaaaaaaaaaa.md", "skills/catalog/example-bbbbbbbbbbbb.md"}
    assert all(entry["into"] == "skills/catalog/example.md" for entry in table.values())
    for old in table:                                                       # moved, never deleted
        assert (nb.root / ".state/archived" / old).is_file()
    assert "../skills/catalog/example.md" in nb.read("notes/links.md")
    assert {m["from"] for m in result["merged"]} == set(table)
    shown = CliRunner().invoke(app, ["rem", "--root", str(nb.root), "show", "skills/catalog/example-aaaaaaaaaaaa.md"])
    assert shown.exit_code == 0 and "Weekly releases" in shown.output


def test_merged_written_pages_renumber_citations():
    from connectonion.rem.merge import merge_text
    kept = ("# P\n\n## Open threads\n- A owes B [1]\n\n## Uncertainties\n- Unknown — not investigated yet\n\n"
            "## Sources\n- [1] mail one\n\nInvestigation: mapped 2026-09-01 · investigated 2026-09-02 (gmail)\n")
    other = ("# P\n\n## Open threads\n- A owes B [3]\n- C waits on D [1]\n\n## Uncertainties\n- Who is C [2]\n\n"
             "## Sources\n- [1] mail two\n- [2] mail three\n- [3] mail four\n\n"
             "Investigation: mapped 2026-09-01 · investigated 2026-09-03 (gmail)\n")
    page = merge_text(kept, other)
    assert "- A owes B [1]\n- C waits on D [2]" in page                     # a repeated line is not doubled
    assert "## Uncertainties\n- Who is C [3]" in page
    assert "- [1] mail one\n- [2] mail two\n- [3] mail three" in page and "mail four" not in page
    assert page.count("Investigation:") == 1


def test_usage_counts_invocations_from_the_users_sessions(tmp_path, monkeypatch):
    """Skill tool calls and /name commands in Claude Code; $name and SKILL.md loads
    in Codex, once per turn; co rem's own runs are not the user's."""
    import json
    source = tmp_path / "installed"
    skill(source, "ship", name="ship-feature")
    skill(source, "quiet", name="never-used")
    call = {"type": "assistant", "uuid": "u1", "timestamp": "2026-09-20T10:00:00Z", "cwd": "/w",
            "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "ship-feature"}}]}}
    command = {"type": "user", "uuid": "u2", "timestamp": "2026-09-21T10:00:00Z", "cwd": "/w",
               "message": {"content": "<command-message>ship</command-message>\n"
                                      "<command-name>/ship-feature</command-name>"}}
    claude = tmp_path / "claude/p/s.jsonl"
    claude.parent.mkdir(parents=True)
    claude.write_text("".join(json.dumps(row) + "\n" for row in (call, command, call)))  # a resumed copy of u1
    rollout = tmp_path / "codex/2026/09/22/rollout-a.jsonl"
    rollout.parent.mkdir(parents=True)
    lines = [{"type": "session_meta", "payload": {"id": "c1", "cwd": "/w"}},
             {"type": "turn_context", "payload": {"cwd": "/w"}},
             {"timestamp": "2026-09-22T09:00:00Z", "type": "response_item", "payload": {
                 "type": "message", "role": "user", "content": [{"type": "input_text", "text": "run $ship-feature"}]}},
             {"timestamp": "2026-09-22T09:00:05Z", "type": "response_item", "payload": {
                 "type": "function_call", "name": "exec_command",
                 "arguments": json.dumps({"cmd": "sed -n 1,80p /h/.codex/skills/ship-feature/SKILL.md"})}},
             {"type": "turn_context", "payload": {"cwd": "/w"}},
             {"timestamp": "2026-09-23T09:00:00Z", "type": "response_item", "payload": {
                 "type": "function_call", "name": "exec_command",
                 "arguments": json.dumps({"cmd": "cat /h/.codex/skills/ship-feature/SKILL.md"})}}]
    rollout.write_text("".join(json.dumps(row) + "\n" for row in lines))
    ours = tmp_path / "codex/2026/09/24/rollout-b.jsonl"
    ours.parent.mkdir(parents=True)
    ours.write_text(json.dumps({"type": "session_meta", "payload": {"id": "c2", "cwd": "/w", "originator": "co_rem"}})
                    + "\n" + json.dumps(lines[2]) + "\n")
    subscriptions = {"claude-code": {"kind": "claude-code", "root": str(tmp_path / "claude")},
                     "codex": {"kind": "codex", "root": str(tmp_path / "codex")}}
    nb = Notebook(tmp_path / "rem")
    map_skills(nb, [source], subscriptions=subscriptions, days=36500)
    page = nb.read("skills/catalog/ship-feature.md")
    usage = page.split("## Usage history\n", 1)[1]
    assert "Invoked 4 times" in usage and "last on 2026-09-23 (Claude Code 2, Codex 2)" in usage
    assert "an invocation is not a completed run" in usage
    assert "No invocation found" in nb.read("skills/catalog/never-used.md")
    assert "used 4×, last 2026-09-23" in nb.read("skills/catalog/index.md")
    cache = json.loads((nb.root / ".state/skill-usage.json").read_text())
    assert "run $ship" not in json.dumps(cache)                              # names and times, never text
    before = nb.read("skills/catalog/ship-feature.md")
    map_skills(nb, [source], subscriptions=subscriptions, days=36500)
    assert nb.read("skills/catalog/ship-feature.md") == before                # cached rerun, same page
