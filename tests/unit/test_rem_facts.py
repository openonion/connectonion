"""Facts as data on every page (#2068): the shape, the upgrade, the review, the coverage."""

import pytest

from connectonion.rem import facts
from connectonion.rem.files import Notebook
from connectonion.rem.page_review import headings, normalize, validate

PERSON = """# Mia Chen

You owe Mia the revised SOW, 12 days. Last contact: 2026-09-10 [2].

## Facts
- Email: mia.chen@harbour.example
- Phone: +61 2 5550 0142 (work) [1]; +61 400 555 019 (mobile) [2]
- Company: [Harbour Analytics](../orgs/harbour.md) [1]
- Role: Head of Data Platform [1]
- Location: Unknown
"""


def test_a_value_its_qualifier_and_its_citations_are_read_apart():
    parsed = facts.parse(PERSON)
    assert parsed["Phone"] == [{"value": "+61 2 5550 0142", "qualifier": "work", "citations": ["1"]},
                               {"value": "+61 400 555 019", "qualifier": "mobile", "citations": ["2"]}]
    assert parsed["Email"] == [{"value": "mia.chen@harbour.example", "qualifier": "", "citations": []}]
    assert parsed["Company"][0]["value"] == "[Harbour Analytics](../orgs/harbour.md)"
    assert parsed["Location"] == []                      # Unknown is an empty list, not a value
    assert parsed["Time zone"] == []                     # a label the page lacks reads as Unknown
    assert list(parsed)[:4] == ["Email", "Phone", "Company", "Role"]


def test_a_citation_covers_the_uncited_values_before_it():
    """A real candidate wrote `Company: UNSW Founders; [UNSW](…) [12]` and was refused for it."""
    parsed = facts.parse("## Facts\n- Company: UNSW Founders; [UNSW](../orgs/unsw.md) [12]\n", "people/t.md")
    assert [v["citations"] for v in parsed["Company"]] == [["12"], ["12"]]
    trailing = facts.parse("## Facts\n- Phone: +61 2 5550 0142 [1]; +61 400 555 019\n", "people/t.md")
    assert trailing["Phone"][1]["citations"] == []          # nothing after it to cover it


def test_a_full_stop_after_the_citation_is_still_a_citation():
    parsed = facts.parse("## Facts\n- How we know them: met at the Sydney meetup [9].\n", "people/t.md")
    assert parsed["How we know them"] == [{"value": "met at the Sydney meetup", "qualifier": "", "citations": ["9"]}]


def test_an_uncited_new_value_is_taken_off_instead_of_refusing_the_page():
    original = "## Facts\n- Role: Lecturer\n- Location: Unknown\n- Email: a@b.example\n"
    candidate = ("## Facts\n- Role: Lecturer\n- Location: Sydney\n- Email: a@b.example\n"
                 "- Phone: +61 2 5550 0142 [1]; +61 400 555 019 (mobile)\n- Time zone: Unknown\n")
    kept, touched = facts.drop_uncited("people/t.md", candidate, original)
    assert "- Location: Unknown" in kept                       # new and uncited: gone
    assert "- Role: Lecturer" in kept                          # carried from the page before: stays
    assert "- Phone: +61 2 5550 0142 [1]\n" in kept            # the cited value stays, the other goes
    assert "- Email: a@b.example" in kept and touched == ["Phone", "Location"]
    assert not any(e.startswith("Fact without") for e in validate("people/t.md", kept, original, []))


def test_a_page_written_before_facts_is_read_from_its_contact_section():
    legacy = PERSON.replace("## Facts", "## Contact")
    assert facts.parse(legacy)["Role"][0]["value"] == "Head of Data Platform"


def test_a_project_and_an_org_have_their_own_fields():
    assert facts.fields("projects/x.md")[0] == "Repository"
    assert "Last activity" in facts.fields("projects/x.md")
    assert facts.fields("orgs/x.md")[0] == "What they do"
    assert facts.fields("notes/x.md") == ()


def test_a_mapped_person_page_opens_on_its_facts_and_insight(tmp_path):
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia Chen", handles=["mia@harbour.example"])
    text = notebook.read("people/mia.md")
    order = [line[3:] for line in text.splitlines() if line.startswith("## ")]
    assert order[:3] == ["Facts", "Insight", "Who they are"]
    assert "## Contact" not in text
    for label in facts.fields("people/mia.md"):
        assert f"\n- {label}: " in text
    assert facts.parse(text)["Handles"][0]["value"] == "mia@harbour.example"


def test_mapped_project_and_org_pages_carry_their_facts(tmp_path):
    notebook = Notebook(tmp_path)
    notebook.stub_project("projects/p.md", "P", paths=["/src/p"])
    notebook.stub_org("orgs/o.md", "O", domains=["o.example"])
    project, org = notebook.read("projects/p.md"), notebook.read("orgs/o.md")
    assert [l for l in project.splitlines() if l.startswith("## ")][:2] == ["## Facts", "## Insight"]
    assert [l for l in org.splitlines() if l.startswith("## ")][:2] == ["## Domains", "## Facts"]
    assert "- Repository: Unknown" in project and "- What they do: Unknown" in org


def test_an_old_page_is_upgraded_without_losing_a_word():
    old = PERSON.replace("## Facts", "## Contact") + "\n## Who they are\n- Leads data [1]\n"
    new = facts.upgrade("people/mia.md", old)
    assert "## Contact" not in new and new.count("## Facts") == 1
    assert "- Phone: +61 2 5550 0142 (work) [1]; +61 400 555 019 (mobile) [2]" in new
    assert "- Time zone: Unknown" in new and "- Also known as: Unknown" in new
    assert new.index("- Location:") < new.index("- Time zone:") < new.index("## Who they are")
    assert facts.upgrade("people/mia.md", new) == new


def test_normalize_puts_facts_and_insight_where_the_reader_expects_them():
    old = PERSON.replace("## Facts", "## Contact") + "\n## Who they are\n- Leads data [1]\n\n## Sources\n- [1] x\n"
    page = normalize("people/mia.md", old)
    found = [line[3:] for line in page.splitlines() if line.startswith("## ")]
    assert found == list(headings("people/mia.md"))
    assert found[:2] == ["Facts", "Insight"]
    assert page.index("You owe Mia") < page.index("## Facts")


def test_the_owners_page_has_facts_and_insight_too():
    """Its Insight is the owner's own month: what shipped, who is waiting (#2065)."""
    assert headings("people/me.md", owner=True)[:2] == ("Facts", "Insight")


def test_coverage_counts_filled_fields():
    got = facts.coverage(PERSON, "people/mia.md")
    assert got == {"filled": 4, "fields": len(facts.fields("people/mia.md"))}


def test_a_page_written_with_the_facts_block_fills_the_people_table_columns(tmp_path):
    """#2073's index reads this block: every #2068 label lands in its column."""
    from connectonion.rem import store
    from connectonion.rem.config import prepare
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/mia.md", "Mia Chen", handles=["mia.chen@harbour.example"],
                         email="mia.chen@harbour.example")
    page = notebook.read("people/mia.md")
    for label, value in (("Phone", "+61 2 5550 0142 (work) [1]; +61 400 555 019 (mobile) [1]"),
                         ("Company", "Harbour Analytics [1]"), ("Role", "Head of Data Platform [1]"),
                         ("Location", "Sydney [1]"), ("Time zone", "AEST (UTC+10) [1]"),
                         ("Links", "https://www.linkedin.com/in/mia-chen [1]; https://harbour.example [1]"),
                         ("How we know them", "introduced by Priya Nair [1]"), ("Language", "English [1]"),
                         ("First contact", "2026-08-04 [1]"), ("Last contact", "2026-09-10 [1]")):
        page = page.replace(f"- {label}: Unknown", f"- {label}: {value}", 1)
    notebook.write("people/mia.md", page.replace("- (none yet)", "- [1] gmail:a1 — 2026-08-04, high"))
    store.refresh(tmp_path)
    mia = store.person(tmp_path, "people/mia.md")
    assert mia["emails"] == ["mia.chen@harbour.example"]
    assert mia["phone"].startswith("+61 2 5550 0142 (work)") and "+61 400 555 019" in mia["phone"]
    assert (mia["company"], mia["role"], mia["location"]) == ("Harbour Analytics", "Head of Data Platform", "Sydney")
    assert mia["timezone"] == "AEST (UTC+10)" and mia["language"] == "English"
    assert mia["linkedin"] == "https://www.linkedin.com/in/mia-chen" and mia["website"] == "https://harbour.example"
    assert mia["how_known"] == "introduced by Priya Nair"
    assert (mia["first_contact"], mia["last_contact"]) == ("2026-08-04", "2026-09-10")


def test_a_link_is_linkedin_by_its_host_not_by_a_substring():
    from connectonion.rem.store_build import columns
    row = columns({"Links": "https://evil.example/?u=linkedin.com; https://www.linkedin.com/in/mia"})
    assert row["linkedin"] == "https://www.linkedin.com/in/mia"
    assert row["website"] == "https://evil.example/?u=linkedin.com"
