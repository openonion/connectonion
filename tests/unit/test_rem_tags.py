"""The Tags line, the one vocabulary and how a query finds a tag (docs/cli/rem-tags.md). Invented data only."""
from connectonion.rem import tags
from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, state_path, write_json

PERSON = """# Mira Osei

## Facts
- Email: mira@harbour.example
- Company: [Harbour University](../orgs/harbour-university.md) [1]
- Unit: COMP9900 team F13 [3]

## Insight
- Now: Presents the F13 demo on Friday [3]

## Sources
- [1] gmail:fixture:1 — 2026-09-01
- [3] gmail:fixture:3 — 2026-09-03
"""


def notebook(tmp_path):
    prepare(tmp_path)
    return Notebook(tmp_path)


def test_the_line_round_trips_with_its_citations():
    rows = [{"tag": "9900", "citation": "3"}, {"tag": "student", "citation": ""}, {"tag": "harbour-university", "citation": "1"}]
    line = tags.format_line(rows)
    assert line == "- Tags: 9900 [3], student, harbour-university [1]"
    assert tags.parse_line(line.removeprefix("- Tags: ")) == rows
    # A session page's uncited line is read by the same parser.
    assert tags.page_tags("## Facts\n- Tags: email, deploy\n") == ["email", "deploy"]


def test_the_line_is_the_last_of_facts_and_nothing_else_moves():
    tagged = tags.with_tags(PERSON, [{"tag": "9900", "citation": "3"}])
    assert "- Unit: COMP9900 team F13 [3]\n- Tags: 9900 [3]\n\n## Insight" in tagged
    assert tags.only_tags_changed(PERSON, tagged)
    assert tags.without_tags(tagged) == PERSON
    retagged = tags.with_tags(tagged, [{"tag": "student", "citation": ""}])
    assert retagged.count("- Tags:") == 1 and tags.page_tags(retagged) == ["student"]
    assert tags.with_tags(tagged, []) == PERSON
    assert not tags.only_tags_changed(PERSON, tagged.replace("Friday", "Monday"))


def test_normalise_is_the_session_rule():
    assert tags.normalise("Capstone 9900") == "capstone-9900"
    assert tags.normalise("tag:COMP9900") == "comp9900"
    assert tags.normalise("  Reader_UI!! ") == "reader-ui"


def test_aliases_label_and_slug_all_resolve_to_one_tag():
    vocabulary = {"9900": {"label": "COMP9900", "kind": "course", "aliases": ["capstone-9900"]},
                  "student": {"label": "student", "kind": "role", "aliases": []}}
    for query in ("9900", "COMP9900", "comp9900", "tag:9900", "tag:comp9900", "Capstone 9900"):
        assert tags.resolve(vocabulary, query) == "9900", query
    assert tags.resolve(vocabulary, "3900") is None
    records = [{"path": "people/mira-osei.md", "text": tags.with_tags(PERSON, [{"tag": "9900", "citation": "3"}])},
               {"path": "people/other.md", "text": "# Other\n"}]
    assert tags.matching(records, vocabulary, "tag:comp9900") == ["people/mira-osei.md"]


def test_vocabulary_merges_session_tags_and_counts_from_pages(tmp_path):
    book = notebook(tmp_path)
    write_json(state_path(tmp_path, "tags.json"), {"tags": {"9900": {"label": "COMP9900", "kind": "course", "aliases": ["comp9900"]}}})
    # Session tags join as topics; one that an alias already names is that tag, not a second one.
    write_json(state_path(tmp_path, "session-tags.json"), {"deploy": 3, "comp9900": 1})
    book.write("people/mira-osei.md", tags.with_tags(PERSON, [{"tag": "9900", "citation": "3"}]))
    book.write("sessions/2026-09-01-a.md", "# A session\n\n## Facts\n- Date: 2026-09-01\n- Tags: deploy, release\n")
    found = tags.vocabulary(tmp_path)
    assert found["9900"] == {"label": "COMP9900", "kind": "course", "aliases": ["comp9900"], "count": 1}
    assert found["deploy"] == {"label": "deploy", "kind": "topic", "aliases": [], "count": 1}
    assert found["release"]["count"] == 1 and "comp9900" not in found
    # The common roles are there from the start, so a person's role needs no new word.
    assert found["student"] == {"label": "student", "kind": "role", "aliases": [], "count": 0}
    # The session page itself is not rewritten.
    assert book.read("sessions/2026-09-01-a.md").endswith("- Tags: deploy, release\n")


def test_an_open_item_inherits_its_record_and_its_person():
    texts = {"projects/f13-demo.md": "# F13 demo\n\n## Facts\n- Tags: demo\n",
             "people/mira-osei.md": tags.with_tags(PERSON, [{"tag": "9900", "citation": "3"}, {"tag": "demo", "citation": ""}])}
    item = "You owe [Mira Osei](../people/mira-osei.md) feedback on the demo [2]"
    assert tags.item_tags(texts, "projects/f13-demo.md", item) == ["demo", "9900"]
    assert tags.item_tags(texts, "people/unknown.md", "nothing linked") == []
