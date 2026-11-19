"""`co rem tag`: what waits, what the model is handed, what review refuses, what is written. Invented data only."""
import json
from pathlib import Path

import pytest

from connectonion.rem import tag_stage, tags
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, RemError, read_json, state_path, write_json
from tests.unit.test_rem_tags import PERSON

ORG = """# Harbour University

## Facts
- Kind: university
- What they do: Runs the COMP9900 capstone course [2]

## Sources
- [2] gmail:fixture:2 — 2026-09-02
"""


@pytest.fixture
def book(tmp_path):
    prepare(tmp_path)
    book = Notebook(tmp_path)
    book.write("people/mira-osei.md", PERSON)
    book.write("orgs/harbour-university.md", ORG)
    book.write("people/stub.md", "# Stub\n\nNo facts yet.\n")
    write_json(state_path(tmp_path, "tags.json"), {"tags": {
        "student": {"label": "student", "kind": "role", "aliases": []},
        "harbour-university": {"label": "Harbour University", "kind": "organisation", "aliases": ["harbour-uni"]}}})
    return book


def reply(pages, new=()):
    return {"pages": pages, "new_tags": list(new)}


COURSE = {"tag": "9900", "label": "COMP9900", "kind": "course", "aliases": ["comp9900"]}
MIRA = [{"tag": "9900", "evidence": "- Unit: COMP9900 team F13 [3]"},
        {"tag": "student", "evidence": "Presents the F13 demo"},
        {"tag": "harbour-uni", "evidence": "- Company: [Harbour University](../orgs/harbour-university.md) [1]"}]


def planned(book, value):
    task = tag_stage.prepare(book.root, ["orgs/harbour-university.md", "people/mira-osei.md"],
                             directory=book.root / "work")
    return task, tag_stage.check(book.root, task, {"result": json.dumps(value)})


def test_pages_with_facts_wait_until_tagged_and_again_once_changed(book):
    assert tag_stage.candidates(book.root) == ["orgs/harbour-university.md", "people/mira-osei.md"]
    task, plan = planned(book, reply([{"id": "p1", "tags": []}, {"id": "p2", "tags": MIRA}], [COURSE]))
    tag_stage.promote(book.root, plan)
    assert tag_stage.candidates(book.root) == []
    # An investigation rewrote the page: it waits again. Its Tags line alone does not count.
    book.write("people/mira-osei.md", book.read("people/mira-osei.md").replace("Friday", "Monday"))
    assert tag_stage.candidates(book.root) == ["people/mira-osei.md"]


def test_the_model_reads_excerpts_and_the_vocabulary_never_sources(book):
    task = tag_stage.prepare(book.root, ["people/mira-osei.md"], directory=book.root / "work")
    page = (book.root / "work/pages/p1.md").read_text()
    assert "## Sources" not in page and "gmail:fixture" not in page and "COMP9900 team F13" in page
    vocabulary = read_json(book.root / "work/vocabulary.json", [])
    assert {row["tag"] for row in vocabulary} == {"harbour-university", *tags.ROLES}
    assert "rem-tag.md" in task["prompt"] and (book.root / "work/rem-tag.md").is_file()
    assert "Reuse first" in (book.root / "work/rem-tag.md").read_text()
    native = tag_stage.prepare(book.root, ["people/mira-osei.md"], directory=book.root / "native", native=True)
    assert native["prompt"].startswith("/rem-tag <co_rem_task>")


def test_review_keeps_supported_tags_with_their_citations_and_merges_aliases(book):
    _, plan = planned(book, reply([{"id": "p1", "tags": [{"tag": "comp9900", "evidence": "Runs the COMP9900 capstone course"}]},
                                   {"id": "p2", "tags": MIRA}], [COURSE]))
    assert plan["pages"]["people/mira-osei.md"]["rows"] == [
        {"tag": "9900", "citation": "3"}, {"tag": "student", "citation": "3"}, {"tag": "harbour-university", "citation": "1"}]
    # `comp9900` is the new course's alias: the org gets `9900`, cited from its line.
    # An organisation page carries its own tag by rule.
    assert plan["pages"]["orgs/harbour-university.md"]["rows"] == [
        {"tag": "9900", "citation": "2"}, {"tag": "harbour-university", "citation": ""}]
    assert plan["new"] == {"9900": {"label": "COMP9900", "kind": "course", "aliases": ["comp9900"]}}
    assert plan["refused"] == []


@pytest.mark.parametrize("row,new,reason", [
    ({"tag": "student", "evidence": "a sentence the page never says"}, [], "no evidence"),
    ({"tag": "student", "evidence": ""}, [], "no evidence"),
    ({"tag": "9900", "evidence": "Presents the F13 demo"}, [COURSE], "not named"),
    ({"tag": "grant", "evidence": "Presents the F13 demo"}, [], "not in vocabulary"),
    ({"tag": "misc", "evidence": "Presents the F13 demo"}, [{"tag": "misc", "label": "Misc", "kind": "topic"}], "bad new tag"),
    ({"tag": "mira-osei", "evidence": "# Mira Osei"}, [{"tag": "mira-osei", "label": "Mira Osei", "kind": "role"}], "bad new tag"),
    ({"tag": "f13", "evidence": "Presents the F13 demo"}, [{"tag": "f13", "label": "F13", "kind": "person"}], "bad new tag"),
])
def test_review_refuses_an_unsupported_tag_and_keeps_the_rest(book, row, new, reason):
    _, plan = planned(book, reply([{"id": "p1", "tags": []},
                                   {"id": "p2", "tags": [row, {"tag": "student", "evidence": "Presents the F13 demo"}]}], new))
    assert plan["refused"] == [{"record": "people/mira-osei.md", "tag": tags.normalise(row["tag"]), "reason": reason}]
    # The organisation her Facts link to is added by rule, cited from that line (and a known course they name).
    added = {row["tag"] for row in plan["added"] if row["tag"] == "9900"}
    assert [row for row in plan["pages"]["people/mira-osei.md"]["rows"] if row["tag"] not in added] == [
        {"tag": "student", "citation": "3"}, {"tag": "harbour-university", "citation": "1"}]


def test_review_caps_new_tags_a_turn_and_tags_a_page(book):
    new = [{"tag": f"topic-{n}", "label": f"Topic {n}", "kind": "topic"} for n in range(10)]
    rows = [{"tag": f"topic-{n}", "evidence": "Presents the F13 demo"} for n in range(10)]
    _, plan = planned(book, reply([{"id": "p1", "tags": []}, {"id": "p2", "tags": rows}], new))
    reasons = [row["reason"] for row in plan["refused"]]
    assert len(plan["new"]) == tag_stage.NEW_PER_TURN
    assert reasons == ["bad new tag: past the turn's cap of new tags"] * (10 - tag_stage.NEW_PER_TURN)
    write_json(state_path(book.root, "tags.json"), {"tags": {
        f"topic-{n}": {"label": f"Topic {n}", "kind": "topic", "aliases": []} for n in range(10)}})
    _, plan = planned(book, reply([{"id": "p1", "tags": []}, {"id": "p2", "tags": rows + rows[:2]}]))
    # The reply's tags stop at PER_PAGE; a tag added by rule (her organisation) comes on top.
    rows = plan["pages"]["people/mira-osei.md"]["rows"]
    assert len(rows) == tag_stage.PER_PAGE + 1 and rows[-1]["tag"] == "harbour-university"
    assert [row["reason"] for row in plan["refused"]] == ["too many"] * (10 - tag_stage.PER_PAGE)


def test_a_reply_without_every_id_is_refused_whole(book):
    with pytest.raises(RemError, match="every page id"):
        planned(book, reply([{"id": "p2", "tags": MIRA}]))
    with pytest.raises(json.JSONDecodeError):
        tag_stage.check(book.root, {"ids": {"p1": "people/mira-osei.md"}, "before": {}}, {"result": "Here are tags"})


def test_promotion_writes_only_the_tags_line_and_skips_a_page_that_changed(book):
    _, plan = planned(book, reply([{"id": "p1", "tags": [{"tag": "harbour-university", "evidence": "# Harbour University"}]},
                                   {"id": "p2", "tags": MIRA}], [COURSE]))
    book.write("orgs/harbour-university.md", ORG.replace("university", "university\n- Location: Unknown", 1))
    assert tag_stage.promote(book.root, plan) == ["people/mira-osei.md"]
    page = book.read("people/mira-osei.md")
    assert tags.page_tags(page) == ["9900", "student", "harbour-university"]
    assert "- Tags: 9900 [3], student [3], harbour-university [1]" in page and tags.only_tags_changed(PERSON, page)
    assert tags.vocabulary(book.root)["9900"]["count"] == 1
    assert tag_stage.candidates(book.root) == ["orgs/harbour-university.md"]


def test_tag_pages_runs_turns_of_twenty_and_records_the_run(book, monkeypatch):
    for n in range(25):
        book.write(f"people/p{n:02}.md", f"# P{n}\n\n## Facts\n- Role: Student in COMP9900 [1]\n")
    calls = []

    def run(directory, prompt, settings, stage):
        ids = sorted(path.stem for path in Path(directory, "pages").iterdir())
        calls.append((stage, len(ids)))
        value = reply([{"id": page, "tags": [{"tag": "student", "evidence": "Student in COMP9900"}]} for page in ids])
        Path(directory, "candidate.json").write_text(json.dumps(value))
        return {"usage": {"input_tokens": 100}}

    monkeypatch.setattr("connectonion.rem.runner.ready", lambda settings: (None, None))
    report = tag_stage.tag_pages(book.root, run=run)
    assert calls == [("tag", 20), ("tag", 7)]
    assert report["tagged"] == 27 and report["failed"] == 0 and report["waiting"] == 0
    assert report["usage"] == {"input_tokens": 200} and report["outcome"] == "completed"
    assert read_json(state_path(book.root, f"runs/{report['id']}.json"), {})["phase"] == "tag"
    assert tags.page_tags(book.read("people/p03.md")) == ["student"]
    assert "Tagged 27 of 27 pages" in tag_stage.summary(report)


def test_a_failed_turn_leaves_its_pages_waiting(book, monkeypatch):
    monkeypatch.setattr("connectonion.rem.runner.ready", lambda settings: (None, None))
    report = tag_stage.tag_pages(book.root, run=lambda *a: {"result": "not json"})
    assert report["failed"] == 2 and report["outcome"] == "failed" and report["waiting"] == 2


def test_rules_add_the_organisation_a_named_team_and_its_course_whatever_the_reply_said(book):
    write_json(state_path(book.root, "tags.json"), {"tags": {
        "9900": {"label": "COMP9900", "kind": "course", "aliases": ["comp9900"]},
        "9900-f13": {"label": "COMP9900 F13", "kind": "team", "aliases": []},
        "9900-f1": {"label": "COMP9900 F1", "kind": "team", "aliases": []}}})
    _, plan = planned(book, reply([{"id": "p1", "tags": []}, {"id": "p2", "tags": []}]))
    assert plan["pages"]["people/mira-osei.md"]["rows"] == [
        {"tag": "harbour-university", "citation": "1"}, {"tag": "9900-f13", "citation": "3"}, {"tag": "9900", "citation": "3"}]
    assert plan["pages"]["orgs/harbour-university.md"]["rows"] == [
        {"tag": "harbour-university", "citation": ""}, {"tag": "9900", "citation": "2"}]
    assert {row["reason"] for row in plan["added"]} == {
        "the organisation's own tag", "an organisation in its Facts", "a team named in its Facts", "a course named in its Facts"}


def test_a_team_is_named_only_by_its_course_and_every_part_as_a_word():
    assert tag_stage._team_named("- Unit: COMP9900 team F13-CAKE [3]", "9900-f13-cake")
    assert not tag_stage._team_named("- Unit: COMP9900 team F13 [3]", "9900-f13-cake")
    assert not tag_stage._team_named("- Unit: COMP3900 team F13 [3]", "9900-f13")
    assert not tag_stage._team_named("- Unit: COMP9900 [3]", "9900")


def test_course_and_team_pages_are_course_and_team_tags_that_their_members_carry(book):
    """The notebook keeps a course and a team as organisation pages (Kind course/team), file names hashed."""
    book.write("orgs/9900-c5a1.md", "# 9900\n\n## Facts\n- Kind: course [1]\n")
    book.write("orgs/9900-f13f-cake-af4d.md", "# 9900-F13F-CAKE\n\n## Facts\n- Kind: team [1]\n- Parent: [[orgs/9900-c5a1.md]] [1]\n")
    book.write("people/mira-osei.md", PERSON.replace("- Unit: COMP9900 team F13 [3]", "- Unit: [[orgs/9900-f13f-cake-af4d.md]] [3]"))
    found = tags.vocabulary(book.root)
    assert found["9900"]["kind"] == "course" and found["9900-f13f-cake"] == {
        "label": "9900-F13F-CAKE", "kind": "team", "aliases": ["9900-f13f-cake-af4d"], "count": 0}
    task = tag_stage.prepare(book.root, ["people/mira-osei.md", "orgs/9900-f13f-cake-af4d.md"], directory=book.root / "work")
    plan = tag_stage.check(book.root, task, {"result": json.dumps(reply([{"id": "p1", "tags": []}, {"id": "p2", "tags": []}]))})
    assert plan["pages"]["people/mira-osei.md"]["rows"] == [
        {"tag": "harbour-university", "citation": "1"}, {"tag": "9900-f13f-cake", "citation": "3"}, {"tag": "9900", "citation": "3"}]
    assert [row["tag"] for row in plan["pages"]["orgs/9900-f13f-cake-af4d.md"]["rows"]] == ["9900-f13f-cake", "9900"]


def test_a_known_course_named_in_the_facts_is_added_and_a_number_inside_another_word_is_not(book):
    write_json(state_path(book.root, "tags.json"), {"tags": {"9900": {"label": "9900", "kind": "course", "aliases": []},
                                                             "990": {"label": "990", "kind": "course", "aliases": []}}})
    _, plan = planned(book, reply([{"id": "p1", "tags": []}, {"id": "p2", "tags": []}]))
    assert {"tag": "9900", "citation": "3"} in plan["pages"]["people/mira-osei.md"]["rows"]
    assert all(row["tag"] != "990" for row in plan["pages"]["people/mira-osei.md"]["rows"])
