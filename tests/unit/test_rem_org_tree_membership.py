"""Who sits inside an organisation's tree (#3397).

The rc19 hunt (2026-11-23): the owner's own co-founder was drawn inside a client's 人物与组织结构 tree,
because the client's page named her under "People here" (she was on the thread). An org page's roster is
the org's claim about who it knows. A person whose OWN page says they work somewhere else, above all at
the owner's own company, is a contact on the owner's side, not a member.
"""
from connectonion.rem.reader_model import organisation_fields, organisation_members

OWNER, MATE, CLIENT_PERSON, MAPPED = ("people/avery.md", "people/kit.md", "people/mara.md", "people/rowan.md")
OWN, CLIENT, UNI, COURSE = "orgs/quillmoor.md", "orgs/fernhill.md", "orgs/example-edu.md", "orgs/1234.md"
SOURCES = "\n## Sources\n- [1] gmail:fixture:1 — 2026-09-01\n"


def _person(path, company=""):
    line = f"- Company: [[{company}]] [1]\n" if company else "- Company: Unknown\n"
    return {"category": "people", "path": path, "title": path, "text": f"# {path}\n\n## Facts\n{line}" + SOURCES}


def _org(path, people=(), kind="client_partner", parent=""):
    roster = "".join(f"- [[{p}]] — on the thread [1]\n" for p in people)
    up = f"- Parent: [[{parent}]] [1]\n" if parent else ""
    return {"category": "orgs", "path": path, "title": path,
            "text": f"# {path}\n\n## Facts\n- Kind: {kind} [1]\n{up}\n## People here\n{roster}" + SOURCES}


def _records(*rows):
    rows = list(rows)
    paths = {row["path"] for row in rows}
    for row in rows:
        row.update(organisation_fields(row, paths))
    return rows


def _by(rows):
    return {row["path"]: row for row in rows}


def test_the_owners_teammate_named_on_a_client_page_is_your_side_not_a_member():
    rows = _records(_person(OWNER, OWN), _person(MATE, OWN), _person(CLIENT_PERSON, CLIENT),
                    _org(OWN, kind="own_company"), _org(CLIENT, people=[MATE, CLIENT_PERSON]))
    organisation_members(rows, OWNER)
    client, mate = _by(rows)[CLIENT], _by(rows)[MATE]
    assert client["people"] == [CLIENT_PERSON]
    assert client["your_side"] == [MATE]
    assert CLIENT not in mate["organisations"]


def test_a_person_whose_own_page_names_another_company_is_not_drawn_in_by_a_roster():
    other = "orgs/harbourline.md"
    rows = _records(_person(OWNER, OWN), _person(MAPPED, other), _org(OWN, kind="own_company"),
                    _org(other), _org(CLIENT, people=[MAPPED]))
    organisation_members(rows, OWNER)
    assert _by(rows)[CLIENT]["people"] == []
    assert _by(rows)[CLIENT]["your_side"] == []


def test_a_roster_still_places_a_person_whose_page_names_no_company():
    rows = _records(_person(OWNER, OWN), _person(MAPPED), _org(OWN, kind="own_company"), _org(CLIENT, people=[MAPPED]))
    organisation_members(rows, OWNER)
    assert _by(rows)[CLIENT]["people"] == [MAPPED]
    assert CLIENT in _by(rows)[MAPPED]["organisations"]


def test_a_roster_on_a_unit_still_places_a_person_whose_company_is_its_parent():
    rows = _records(_person(OWNER, OWN), _person(MAPPED, UNI), _org(OWN, kind="own_company"),
                    _org(UNI, kind="university"), _org(COURSE, people=[MAPPED], kind="course", parent=UNI))
    organisation_members(rows, OWNER)
    assert _by(rows)[COURSE]["people"] == [MAPPED]


def test_the_owners_teammates_stay_members_of_the_owners_own_company():
    rows = _records(_person(OWNER, OWN), _person(MATE, OWN), _org(OWN, people=[MATE], kind="own_company"))
    organisation_members(rows, OWNER)
    assert _by(rows)[OWN]["people"] == [MATE]
    assert _by(rows)[OWN]["your_side"] == []
