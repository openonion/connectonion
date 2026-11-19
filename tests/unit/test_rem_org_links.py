"""A person's organisations are pages, linked both ways (#3141).

Owner, 2026-11-19, after investigating a person: "为什么上面没有建 One 这个组织？为什么没有把 One 双向链接到一块？"
"""

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook
from connectonion.rem.org_links import link_orgs, new_org_links, org_errors
from connectonion.rem.page_review import validate


def _person(root):
    notebook = Notebook(root)
    notebook.stub_person("people/petra.md", "Petra Lind", ["petra@one.example"], email="petra@one.example")
    return notebook, notebook.read("people/petra.md")


def _with(original, company="Unknown", who="- Unknown — not investigated yet", sources="- [1] gmail:aaaaaaaaaaaa — 2026-10-01"):
    return (original.replace("- Company: Unknown", f"- Company: {company}")
            .replace("## Who they are\n- Unknown — not investigated yet", f"## Who they are\n{who}")
            .replace("- (none yet)", sources))


def test_a_new_career_line_or_company_must_name_its_organisation_by_its_page(tmp_path):
    prepare(tmp_path)
    _, original = _person(tmp_path)
    bare = _with(original, company="One Consulting [1]",
                 who="Petra founded an IT consultancy. [1]\n- 2019–now: Founder, One Consulting — IT consulting for councils [1]")
    errors = org_errors("people/petra.md", bare, original)
    assert any("Company" in e and "../orgs/" in e for e in errors), errors
    assert any("2019–now" in e for e in errors), errors
    linked = _with(original, company="[One Consulting](../orgs/one-consulting.md) [1]",
                   who="Petra founded an IT consultancy. [1]\n- 2019–now: Founder, [One Consulting](../orgs/one-consulting.md) — IT consulting [1]")
    assert org_errors("people/petra.md", linked, original) == []
    # validate carries it, so the repair loop is asked to fix it
    assert any("../orgs/" in e for e in validate("people/petra.md", bare, original, [], root=tmp_path))


def test_a_line_the_page_already_had_is_not_this_runs_to_fix(tmp_path):
    prepare(tmp_path)
    _, stub = _person(tmp_path)
    original = _with(stub, company="One Consulting [1]", who="- 2019–now: Founder, One Consulting [1]")
    assert org_errors("people/petra.md", original, original) == []
    assert org_errors("people/petra.md", _with(stub, company="Unknown"), stub) == []
    assert org_errors("orgs/one.md", "# One\n", "# One\n") == []


def test_saving_a_person_creates_missing_organisations_and_links_them_back(tmp_path):
    prepare(tmp_path)
    notebook, original = _person(tmp_path)
    notebook.stub_org("orgs/unsw.md", "UNSW", ["unsw.edu.au"])
    text = _with(original, company="[One Consulting](../orgs/one-consulting.md) [1]",
                 who="- 2019–now: Founder, [One Consulting](../orgs/one-consulting.md) [1]\n"
                     "- 2010–2014: BSc, [UNSW](../orgs/unsw.md) [1]")
    notebook.write("people/petra.md", text)
    done = link_orgs(notebook, "people/petra.md", text)
    assert {(d["record"], d["created"]) for d in done} == {("orgs/one-consulting.md", True), ("orgs/unsw.md", False)}
    created = notebook.read("orgs/one-consulting.md")
    assert created.startswith("# One Consulting\n") and "not investigated yet" in created  # queued for the night's --quick
    for org in ("orgs/one-consulting.md", "orgs/unsw.md"):
        people = notebook.read(org).split("## People here\n", 1)[1].split("\n## ", 1)[0]
        assert "[Petra Lind](../people/petra.md)" in people, org
        assert "Unknown — not investigated yet" not in people
    # a second save adds nothing twice
    assert all(not d["created"] for d in link_orgs(notebook, "people/petra.md", text))
    assert notebook.read("orgs/unsw.md").count("../people/petra.md") == 1


def test_what_changed_names_the_organisations_a_run_linked():
    before = "# P\n\n## Who they are\n- 2019: Founder, [Old Co](../orgs/old.md) [1]\n"
    after = before + "- 2010: Analyst, [New Co](../orgs/new-co.md) [2]\n"
    assert new_org_links(before, after) == [{"title": "New Co", "record": "orgs/new-co.md"}]


def test_a_promoted_person_page_creates_and_links_its_organisations(tmp_path):
    """Through the runner's own save path: the page the turn wrote names a new organisation by its page."""
    from connectonion.rem import runner
    prepare(tmp_path)
    notebook, original = _person(tmp_path)
    items = [{"source": "gmail:aaaaaaaaaaaa", "text": "Petra founded One Consulting in 2019 and runs IT for councils."}]
    draft = _with(original, company="[One Consulting](../orgs/one-consulting.md) [1]",
                  who="Petra runs an IT consultancy for councils. [1]\n- 2019–now: Founder, [One Consulting](../orgs/one-consulting.md) [1]")
    path = tmp_path / "candidate.md"
    path.write_text(draft)
    page = [{"role": "page", "record": "people/petra.md", "append": True, "source": "investigation:page", "text": original}]
    runner._promote_candidate(notebook, "people/petra.md", path, original, [*page, *items], tmp_path, None, carried=original)
    assert "[One Consulting](../orgs/one-consulting.md)" in notebook.read("people/petra.md")
    assert "[Petra Lind](../people/petra.md)" in notebook.read("orgs/one-consulting.md")
