"""The #2068 benchmark fixtures say what they claim to, and check_pages catches what it must."""

import importlib.util
import re
from pathlib import Path

from connectonion.benchmark.suite import load
from connectonion.rem import facts
from connectonion.rem.fact_extract import extract

BENCH = Path(__file__).resolve().parents[2] / "examples" / "rem-skill-evals" / ".co" / "benchmarks"
spec = importlib.util.spec_from_file_location("check_pages", BENCH / "check_pages.py")
check_pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_pages)


def rows(case, handles):
    return extract(check_pages.material_items(BENCH / "fixtures" / case / "material.md"), handles)


def test_two_phones_in_a_signature_are_read_with_their_labels():
    found = rows("person-phones", ["priya.raman@lumenops.example", "Priya Raman"])
    assert [(r["value"], r["qualifier"]) for r in found if r["field"] == "Phone"] == [
        ("+61 2 5550 0177", "work"), ("+61 455 500 912", "mobile")]
    assert any(r["field"] == "Links" for r in found)


def test_a_role_only_in_an_invite_and_a_company_only_in_a_domain_are_handed_over():
    invite = rows("person-invite", ["sam@corellafoods.example", "Sam Okafor"])
    assert any(r["field"] == "Calendar" and "Head of Procurement" in r["value"] for r in invite)
    domain = rows("person-domain", ["lena.hart@brightwave-energy.example", "Lena Hart"])
    assert [r["value"] for r in domain if r["field"] == "Company domain"] == ["brightwave-energy.example"]


def test_a_page_that_left_the_phones_off_is_reported():
    page = (BENCH / "fixtures" / "person-phones" / "page.md").read_text()
    lost = check_pages.lost_facts("people/person-phones.md", page,
                                  check_pages.material_items(BENCH / "fixtures" / "person-phones" / "material.md"),
                                  page)
    fields = {r["field"] for r in lost}
    assert fields >= {"Phone", "Links", "First contact", "Last contact"}


def test_generic_or_unlabelled_insight_is_refused_and_a_labelled_one_passes():
    good = "## Insight\n- At stake: the user has owed Priya the quote since 2026-09-12 [3]\n\n## Who they are\n"
    assert check_pages.insight_problems(good) == []
    generic = "## Insight\n- Now: Priya is a key stakeholder [1]\n\n## Who they are\n"
    assert any("generic filler" in p for p in check_pages.insight_problems(generic))
    unlabelled = "## Insight\n- Priya wants a quote [1]\n\n## Who they are\n"
    assert any("not labelled" in p for p in check_pages.insight_problems(unlabelled))


def test_every_fixture_page_is_already_in_the_facts_shape():
    obsidian, problems = load("rem-source-obsidian", root=BENCH.parents[1])
    assert not problems, problems
    records = {}
    for case in obsidian.cases:
        match = re.match(r"Maintain only the Wiki record (\S+\.md) ", case.input)
        assert match, case.id
        page = BENCH / case.fixture / "page.md"
        assert page.is_file(), case.id
        records[page] = match[1]

    for page in (BENCH / "fixtures").glob("*/page.md"):
        record = records.get(page)
        if record is None:
            kind = "people" if page.parent.name.startswith("person-") else "projects"
            record = f"{kind}/{page.parent.name}.md"
        content = page.read_text(encoding="utf-8")
        assert facts.upgrade(record, content) == content, page.parent.name
