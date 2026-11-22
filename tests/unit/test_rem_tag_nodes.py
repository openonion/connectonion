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
    assert read_json(state_path(book.root, f"runs/{report['id']}.json"), {})["phase"] == "investigate"  # a tag page is investigated (#3140)


def test_tag_dry_run_counts_and_investigate_tag_writes_only_that_tags_page(book, monkeypatch):
    """#3140's final CLI (owner, 2026-11-19): `co rem tag --dry-run` counts with no model; `co rem investigate tag
    NAME` (or its alias topic) writes that tag's page only, with no tagging turn."""
    import json
    from typer.testing import CliRunner
    from connectonion.cli.main import app
    from connectonion.rem import runner, tag_stage
    monkeypatch.setattr(runner, "run_task", lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry run called a model")))
    cli = CliRunner()
    plan = json.loads(cli.invoke(app, ["rem", "--root", str(book.root), "--json", "tag", "--dry-run"]).output)["data"]
    assert plan["waiting"] == 1 and plan["tags_linked_to_pages"] == 0 and plan["untagged_waiting"] == len(tag_stage.candidates(book.root))
    calls = []

    def run(directory, prompt, settings, stage):
        calls.append(stage)
        Path(run.task["candidate"]).write_text(reply(run.task, NODE)["result"])
        return {"result": "", "usage": {}}
    real = tag_nodes.prepare
    monkeypatch.setattr(tag_nodes, "prepare", lambda *a, **k: setattr(run, "task", real(*a, **k)) or run.task)
    monkeypatch.setattr(runner, "run_task", run)
    monkeypatch.setattr(runner, "ready", lambda settings: ("", ""))
    data = json.loads(cli.invoke(app, ["rem", "--root", str(book.root), "--json", "investigate", "topic", "Kiln pilot"]).output)["data"]
    assert calls == ["tag-node"] and data["page"] == "knowledge/kiln-pilot.md" and data["written"] == ["knowledge/kiln-pilot.md"]
    assert book.read("knowledge/kiln-pilot.md").startswith("# Kiln pilot")
    text = cli.invoke(app, ["rem", "--root", str(book.root), "tag", "--dry-run"]).output
    assert "tags get a tag page" in text and "node" not in text and "graph" not in text


def test_a_tag_named_for_a_page_links_to_it_and_needs_no_topic_page(book):
    """#3140: one kind of point, the page. A tag that names an organisation (by title, alias or file name) is a link
    to that page; only a tag no page is named for gets a topic page."""
    write_json(state_path(book.root, "tags.json"), {"tags": {
        "kiln-pilot": {"label": "Kiln pilot", "kind": "project", "aliases": []},
        "harbour": {"label": "Harbour Labs", "kind": "organisation", "aliases": []}}})
    book.write("people/lena-brandt.md", PILOT.replace("- Tags: kiln-pilot [1]", "- Tags: kiln-pilot [1], harbour [1]"))
    book.write("people/theo-park.md", LONE.replace("harbour-rowing", "harbour"))
    assert tag_nodes.pages_for_tags(book.root)["harbour"] == "orgs/harbour-labs.md"   # by the page's title
    assert "harbour" not in tag_nodes.candidates(book.root)
    plan = tag_nodes.dry_run(book.root)
    assert plan["tags_linked_to_pages"] >= 1 and plan["tag_pages_possible"] == 1
    report = tag_nodes.write_nodes(book.root, only="harbour", ready=lambda settings: ("", ""))
    assert report["linked"] == {"harbour": "orgs/harbour-labs.md"} and report["written"] == []


def test_the_owners_example_three_tags_link_to_their_pages_and_one_gets_a_topic_page(tmp_path):
    """Owner, 2026-11-19: a person tagged UNSW, OpenOnion, ConnectOnion and "AI Agent" links the first three to their
    existing organisation and project pages; "AI Agent", which no page is named for, gets one topic page written
    from every page carrying it. A tag on a single page stays a plain link."""
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.write("orgs/unsw-1a2b3c4d5e.md", "# UNSW\n\n## Facts\n- Kind: university\n\n## Sources\n- [1] gmail:fx:1\n")
    book.write("orgs/openonion.md", "# OpenOnion\n\n## Facts\n- Kind: company\n\n## Sources\n- [1] gmail:fx:2\n")
    book.write("projects/connectonion.md", "# ConnectOnion\n\n## What it is\nThe agent framework [1].\n\n## Sources\n- [1] codex:fx:3\n")
    tagged = "- Tags: unsw [1], openonion [1], connectonion [1], ai-agent [1]"
    book.write("people/rin-sato.md", f"# Rin Sato\n\n## Facts\n- Role: Student [1]\n{tagged}\n\n## Who they are\nRin builds agents [1].\n\n## Sources\n- [1] gmail:fx:4\n")
    book.write("people/kai-moss.md", "# Kai Moss\n\n## Facts\n- Tags: ai-agent [1], kiln [1]\n\n## Who they are\nKai studies agent memory [1].\n\n## Sources\n- [1] gmail:fx:5\n")
    write_json(state_path(tmp_path, "tags.json"), {"tags": {
        "unsw": {"label": "UNSW", "kind": "organisation", "aliases": []},
        "openonion": {"label": "OpenOnion", "kind": "organisation", "aliases": []},
        "connectonion": {"label": "ConnectOnion", "kind": "project", "aliases": []},
        "ai-agent": {"label": "AI Agent", "kind": "topic", "aliases": []},
        "kiln": {"label": "Kiln", "kind": "topic", "aliases": []}}})
    named = tag_nodes.pages_for_tags(tmp_path)
    assert named["unsw"] == "orgs/unsw-1a2b3c4d5e.md"           # by title, through a hashed file name
    assert named["openonion"] == "orgs/openonion.md" and named["connectonion"] == "projects/connectonion.md"
    assert "ai-agent" not in named and tag_nodes.candidates(tmp_path) == ["ai-agent"]
    plan = tag_nodes.dry_run(tmp_path)
    assert plan["tags_linked_to_pages"] == 3 and plan["tag_pages_possible"] == 1 and plan["single_page_tags"] == 1
    task = tag_nodes.prepare(tmp_path, "ai-agent", directory=tmp_path / "work")
    handed = (tmp_path / "work" / "members.md").read_text()
    assert "Rin builds agents" in handed and "Kai studies agent memory" in handed
    n = task["numbers"][0]
    Path(task["candidate"]).write_text(f"# AI Agent\n\nAgent work that Rin and Kai share [{n}].\n")
    assert tag_nodes.commit(tmp_path, task, tag_nodes.check(tmp_path, task, {})) == ["knowledge/ai-agent.md"]
    assert "[Kai Moss](../people/kai-moss.md)" in book.read("knowledge/ai-agent.md")
    assert not book.exists("knowledge/unsw.md") and not book.exists("knowledge/kiln.md")


# ---------- a tag page's title never carries a privacy mark (#3385) ----------
# At the default "cover" level the reader shows a marked title as the generic "Personal", so five marked tag
# pages (a language, a CLI, email, documents, sleep) became one repeated label and a link that opened the wrong page.

@pytest.mark.parametrize("mark", ["[personal]", "[sensitive]", "［personal］"])
def test_review_refuses_a_tag_page_whose_title_carries_a_privacy_mark(book, tmp_path, mark):
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work")
    Path(task["candidate"]).write_text(reply(task, NODE.replace("# Kiln pilot", f"# Kiln pilot {mark}"))["result"])
    with pytest.raises(RemError, match="title never carries"):
        tag_nodes.check(book.root, task, {})


def test_a_rewrite_of_a_marked_tag_page_writes_its_title_without_the_mark(book, tmp_path):
    book.write("knowledge/kiln-pilot.md", "# Kiln pilot [personal]\n\nAn older note on the pilot [1].\n\n## Sources\n- [1] gmail:fixture:ee01\n")
    task = tag_nodes.prepare(book.root, "kiln-pilot", directory=tmp_path / "work")
    Path(task["candidate"]).write_text(reply(task, NODE)["result"])
    tag_nodes.commit(book.root, task, tag_nodes.check(book.root, task, {}))
    page = book.read("knowledge/kiln-pilot.md")
    assert page.splitlines()[0] == "# Kiln pilot"
    assert page.count("\n# ") == 0  # the old marked title is not kept as a lost line


MARKED_TAG = """# Kiln pilot [personal]

The kiln pilot is a trial with Harbour Labs [1].

## How they connect
- Lena Brandt leads it [1].
- Already private [2] [sensitive]

- Tags: kiln-pilot

## Pages
- [Lena Brandt](../people/lena-brandt.md)

Investigation: investigated 2026-11-20 (tag page, from 2 pages)

## Sources
- [1] gmail:fixture:aa01
- [2] gmail:fixture:aa02
"""
DIARY = "# Night notes [personal]\n\nA private topic, not a tag page [1].\n\n## Sources\n- [1] gmail:fixture:ff01\n"


def test_the_repair_unmarks_tag_titles_once_and_keeps_their_passages_private(book):
    book.write("knowledge/kiln-pilot.md", MARKED_TAG)
    book.write("knowledge/night-notes.md", DIARY)
    assert tag_nodes.repair_titles(book.root) == ["knowledge/kiln-pilot.md"]
    page = book.read("knowledge/kiln-pilot.md")
    assert page.splitlines()[0] == "# Kiln pilot"
    # The title's mark moves onto every prose passage, so nothing private becomes public by the repair.
    assert "The kiln pilot is a trial with Harbour Labs [1]. [personal]" in page
    assert "- Lena Brandt leads it [1]. [personal]" in page
    assert "- Already private [2] [sensitive]" in page  # already marked: left as it was
    # What code owns stays unmarked: headings, the Tags line, the member list, the stamp and the sources.
    assert "## How they connect\n" in page and "- [Lena Brandt](../people/lena-brandt.md)\n" in page
    assert "- [1] gmail:fixture:aa01\n" in page and "(tag page, from 2 pages)\n" in page
    # A private topic that is not a tag's page keeps its title mark: it is private as a whole.
    # (It was the second masked page written, so it carries "Masked: 2"; masked.py.)
    assert book.read("knowledge/night-notes.md") == DIARY.replace("\n", "\nMasked: 2\n", 1)
    assert "Masked:" not in page  # an unmasked tag page's own name is its label again
    # Idempotent: a second build finds no marked tag title and writes nothing.
    assert tag_nodes.repair_titles(book.root) == []


def test_the_repair_writes_nothing_where_there_is_nothing_to_repair(tmp_path, book):
    # A notebook that does not exist yet stays absent (opening before start creates nothing).
    missing = tmp_path / "not-started"
    assert tag_nodes.repair_titles(missing) == [] and not missing.exists()
    # A notebook with only unmarked pages: no state file appears, no page changes.
    book.write("knowledge/kiln-pilot.md", NODE)
    before = book.read("knowledge/kiln-pilot.md")
    state = sorted(p.name for p in (book.root / ".state").iterdir())
    assert tag_nodes.repair_titles(book.root) == []
    assert book.read("knowledge/kiln-pilot.md") == before
    assert sorted(p.name for p in (book.root / ".state").iterdir()) == state


def test_the_repair_keeps_the_marked_page_for_undo(book):
    from connectonion.rem import page_versions
    book.write("knowledge/kiln-pilot.md", MARKED_TAG)
    tag_nodes.repair_titles(book.root)
    assert page_versions.previous(book.root, "knowledge/kiln-pilot.md")["text"] == MARKED_TAG.replace("\n", "\nMasked: 1\n", 1)
