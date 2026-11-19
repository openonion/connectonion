"""`co rem graph` step 2 (#3140): each tag's knowledge node, written from the pages that carry it. Invented data only."""
from pathlib import Path

import pytest

from connectonion.rem import tag_nodes, tags
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, read_json, state_path, write_json

PILOT = """# Lena Brandt

## Facts
- Company: Harbour Labs [1]
- Tags: kiln-pilot [1]

## Who they are
Lena leads the kiln pilot at Harbour Labs [1]. She asked for a second kiln in October [2].

## Sources
- [1] gmail:fixture:aa01 — 2026-09-01
- [2] gmail:fixture:aa02 — 2026-10-03
"""
ORG = """# Harbour Labs

## Facts
- Kind: company
- Tags: kiln-pilot [1]

## Who they are
Harbour Labs makes ceramic kilns; its pilot with you began in September [1].

## Sources
- [1] outlook:fixture:bb01 — 2026-09-04
"""
LONE = "# Theo Park\n\n## Facts\n- Tags: harbour-rowing [1]\n\n## Who they are\nTheo rows [1].\n\n## Sources\n- [1] gmail:fixture:cc01\n"
UNTAGGED = "# Ines Vale\n\n## Facts\n- Company: Unknown\n\n## Who they are\nInes asked about pricing [1].\n\n## Sources\n- [1] gmail:fixture:dd01\n"


@pytest.fixture
def book(tmp_path):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.write("people/lena-brandt.md", PILOT)
    book.write("orgs/harbour-labs.md", ORG)
    book.write("people/theo-park.md", LONE)
    book.write("people/ines-vale.md", UNTAGGED)
    write_json(state_path(tmp_path, "tags.json"), {"tags": {
        "kiln-pilot": {"label": "Kiln pilot", "kind": "project", "aliases": []},
        "harbour-rowing": {"label": "Harbour rowing", "kind": "topic", "aliases": []}}})
    return book


def reply(task, body):
    return {"result": body.format(**{f"g{i}": n for i, n in enumerate(task["numbers"], 1)})}


NODE = """# Kiln pilot

The kiln pilot is Harbour Labs' trial of its ceramic kilns with you, led by Lena Brandt [{g1}].

## How they connect
- Lena Brandt leads it for Harbour Labs [{g1}].

## Timeline
- 2026-09-04: the pilot began [{g3}].
- 2026-10-03: Lena asked for a second kiln [{g2}].
"""


def test_a_tag_carried_by_two_or_more_pages_waits_and_one_alone_does_not(book):
    assert tag_nodes.members(book.root)["kiln-pilot"] == ["orgs/harbour-labs.md", "people/lena-brandt.md"]
    assert tag_nodes.candidates(book.root) == ["kiln-pilot"]  # harbour-rowing has one page: no node yet
    assert tag_nodes.orphans(book.root) == ["people/ines-vale.md"]


def test_the_model_reads_each_members_head_with_its_sources_renumbered_once(book, tmp_path):
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work")
    handed = (tmp_path / "work" / "members.md").read_text()
    assert "Lena leads the kiln pilot" in handed and "Harbour Labs makes ceramic kilns" in handed
    # Every member's [n] is one notebook-wide number with its definition, so a cited line can be traced.
    assert set(task["sources"]) == {str(n) for n in task["numbers"]} and len(task["numbers"]) == 3
    assert "Kiln pilot" in task["prompt"] and str(task["candidate"]) in task["prompt"]


def test_the_node_is_written_with_code_owned_tags_members_and_sources(book, tmp_path):
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work")
    Path(task["candidate"]).write_text(reply(task, NODE)["result"])
    written = tag_nodes.commit(book.root, task, tag_nodes.check(book.root, task, {}))
    page = book.read("knowledge/kiln-pilot.md")
    assert written == ["knowledge/kiln-pilot.md"]
    assert tags.page_tags(page) == ["kiln-pilot"]
    assert "[Lena Brandt](../people/lena-brandt.md)" in page and "[Harbour Labs](../orgs/harbour-labs.md)" in page
    assert "gmail:fixture:aa02" in page and "outlook:fixture:bb01" in page  # real provenance, not page names
    assert tag_nodes.candidates(book.root) == []  # incremental: unchanged members, no new turn


def test_a_member_that_changes_makes_its_tag_wait_again(book, tmp_path):
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work")
    Path(task["candidate"]).write_text(reply(task, NODE)["result"])
    tag_nodes.commit(book.root, task, tag_nodes.check(book.root, task, {}))
    book.write("people/lena-brandt.md", PILOT.replace("October", "November"))
    assert tag_nodes.candidates(book.root) == ["kiln-pilot"]


@pytest.mark.parametrize("bad, why", [
    ("# Kiln pilot\n\nIt is a pilot.\n", "no cited line"),
    ("# Kiln pilot\n\nIt is a pilot [999].\n", r"cites \[999\]"),
    ("Kiln pilot without a title [{g1}].\n", "one title"),
])
def test_review_refuses_a_node_without_citations_or_a_title(book, tmp_path, bad, why):
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work")
    Path(task["candidate"]).write_text(reply(task, bad)["result"])
    with pytest.raises(RemError, match=why):
        tag_nodes.check(book.root, task, {})


def test_an_existing_node_keeps_every_cited_line_it_had(book, tmp_path):
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work")
    Path(task["candidate"]).write_text(reply(task, NODE)["result"])
    tag_nodes.commit(book.root, task, tag_nodes.check(book.root, task, {}))
    book.write("people/lena-brandt.md", PILOT.replace("October", "November"))
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work2")
    shorter = "# Kiln pilot\n\nThe kiln pilot is a trial with Harbour Labs [{g1}].\n"
    Path(task["candidate"]).write_text(reply(task, shorter)["result"])
    tag_nodes.commit(book.root, task, tag_nodes.check(book.root, task, {}))
    # The append rule (#3105): a line the node had, cited, survives a rewrite that dropped it.
    assert "Lena asked for a second kiln" in book.read("knowledge/kiln-pilot.md")


def test_a_matching_knowledge_entry_is_the_tags_node(book, tmp_path):
    book.write("knowledge/kiln-pilot.md", "# Kiln pilot\n\nAn older note on the pilot [1].\n\n## Sources\n- [1] gmail:fixture:ee01\n")
    assert tag_nodes.node_record(book.root, "kiln-pilot") == "knowledge/kiln-pilot.md"
    assert "knowledge/kiln-pilot.md" not in tag_nodes.members(book.root).get("kiln-pilot", [])
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work")
    assert "An older note on the pilot" in Path(task["before_file"]).read_text()


def test_dry_run_counts_tags_members_orphans_and_estimates_tokens_without_a_model(book):
    plan = tag_nodes.dry_run(book.root)
    assert plan["tags"] == 2 and plan["waiting"] == 1 and plan["orphans"] == 1
    assert plan["members"]["kiln-pilot"] == 2 and plan["estimated_input_tokens"] > 0


def test_write_nodes_runs_one_turn_per_waiting_tag_and_records_the_run(book):
    def run(directory, prompt, settings, stage):
        task = run.task
        Path(task["candidate"]).write_text(reply(task, NODE)["result"])
        return {"result": "", "usage": {"input_tokens": 100}}
    real = tag_nodes.prepare

    def capture(*args, **kwargs):
        run.task = real(*args, **kwargs)
        return run.task
    tag_nodes.prepare = capture
    try:
        report = tag_nodes.write_nodes(book.root, run=run, ready=lambda settings: (None, None))
    finally:
        tag_nodes.prepare = real
    assert report["written"] == ["knowledge/kiln-pilot.md"] and report["failed"] == 0
    assert read_json(state_path(book.root, f"runs/{report['id']}.json"), {})["phase"] == "tag"


def test_co_rem_tag_dry_run_counts_without_a_model_and_one_tag_writes_only_its_page(book, monkeypatch):
    """#3140's CLI (owner, 2026-11-19): one verb. `co rem tag` tags, then writes tag pages; NAME writes one; --dry-run counts."""
    import json
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import runner, tag_stage
    monkeypatch.setattr(runner, "run_task", lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry run called a model")))
    cli = CliRunner()
    plan = json.loads(cli.invoke(app, ["rem", "--root", str(book.root), "--json", "tag", "--dry-run"]).output)["data"]
    assert plan["waiting"] == 1 and plan["untagged_waiting"] == len(tag_stage.candidates(book.root))
    calls = []

    def run(directory, prompt, settings, stage):
        calls.append(stage)
        task = run.task
        Path(task["candidate"]).write_text(reply(task, NODE)["result"])
        return {"result": "", "usage": {}}
    real = tag_nodes.prepare
    monkeypatch.setattr(tag_nodes, "prepare", lambda *a, **k: setattr(run, "task", real(*a, **k)) or run.task)
    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(runner, "ready", lambda settings: ("", ""))
    result = cli.invoke(app, ["rem", "--root", str(book.root), "--json", "tag", "kiln-pilot"])
    data = json.loads(result.output)["data"]
    assert calls == ["tag-node"]  # NAME writes that tag's page only: no tagging turn
    assert {"tagged", "tag_pages_written", "untagged", "next"} <= set(data)
    assert data["tag_pages_written"] == 1 and data["untagged"] == 1 and data["next"] == "co rem open"
    text = cli.invoke(app, ["rem", "--root", str(book.root), "tag", "kiln-pilot"]).output
    assert "pages · " in text and "tag pages written" in text and "node" not in text and "graph" not in text
