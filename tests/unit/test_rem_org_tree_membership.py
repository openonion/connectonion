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


# Real-shaped pages (#3397 reopened, rc21 hunt 2026-11-23): on the owner's real notebook the owner page's
# Company is plain text, not a link; no org page says `Kind: own_company`; and the owner's teammates' pages
# carry an Email at the owner's domain but no Company line. #3400's rule needed an explicit Company on the
# teammate's page, so the fixture above passed while 0 of 73 real orgs showed 「你这边对接的人」.

def _real_owner(company_text, email):
    return {"category": "people", "path": OWNER, "title": "Avery Quill",
            "text": f"# Avery Quill\n\n## Facts\n- Email: {email} [1]\n- Company: {company_text} [1]\n" + SOURCES}


def _real_mate(path, email):
    return {"category": "people", "path": path, "title": path,
            "text": f"# {path}\n\n## Facts\n- Email: {email} [1]\n" + SOURCES}


def _real_org(path, title, people=(), kind=""):
    roster = "".join(f"- [[{p}]] — on the thread [1]\n" for p in people)
    kind_line = f"- Kind: {kind} [1]\n" if kind else ""
    return {"category": "orgs", "path": path, "title": title,
            "text": f"# {title}\n\n## Facts\n{kind_line}\n## People here\n{roster}" + SOURCES}


def test_a_teammate_with_no_company_line_but_the_owners_mail_domain_is_your_side():
    rows = _records(_real_owner("Quillmoor Labs (co-founder)", "avery@quillmoor.example"),
                    _real_mate(MATE, "kit@quillmoor.example"), _person(CLIENT_PERSON, CLIENT),
                    _real_org(OWN, "Quillmoor Labs"), _real_org(CLIENT, "Fernhill", people=[MATE, CLIENT_PERSON]))
    organisation_members(rows, OWNER)
    client = _by(rows)[CLIENT]
    assert client["people"] == [CLIENT_PERSON]
    assert client["your_side"] == [MATE]
    assert CLIENT not in _by(rows)[MATE]["organisations"]


def test_the_owners_plain_text_company_names_the_owners_org():
    """The owner's Company written as plain text still makes that org the owner's side."""
    rows = _records(_real_owner("Quillmoor Labs", "avery@gmail.com"), _person(MATE, OWN),
                    _real_org(OWN, "Quillmoor Labs"), _real_org(CLIENT, "Fernhill", people=[MATE]))
    organisation_members(rows, OWNER)
    assert _by(rows)[CLIENT]["your_side"] == [MATE]


def test_a_free_mail_domain_is_never_the_owners_side():
    rows = _records(_real_owner("Quillmoor Labs", "avery@gmail.com"), _real_mate(MAPPED, "rowan@gmail.com"),
                    _real_org(OWN, "Quillmoor Labs"), _real_org(CLIENT, "Fernhill", people=[MAPPED]))
    organisation_members(rows, OWNER)
    assert _by(rows)[CLIENT]["people"] == [MAPPED]
    assert _by(rows)[CLIENT]["your_side"] == []


def test_a_mail_domain_teammate_whose_own_company_is_a_client_stays_there():
    """The person's own Company line wins over the shared domain (they may have moved)."""
    rows = _records(_real_owner("Quillmoor Labs", "avery@quillmoor.example"),
                    {"category": "people", "path": MATE, "title": MATE,
                     "text": f"# {MATE}\n\n## Facts\n- Email: kit@quillmoor.example [1]\n- Company: [[{CLIENT}]] [1]\n" + SOURCES},
                    _real_org(OWN, "Quillmoor Labs"), _real_org(CLIENT, "Fernhill", people=[MATE]))
    organisation_members(rows, OWNER)
    assert _by(rows)[CLIENT]["people"] == [MATE]
    assert _by(rows)[CLIENT]["your_side"] == []


def test_mail_domain_teammates_are_members_of_the_owners_own_org():
    rows = _records(_real_owner("Quillmoor Labs", "avery@quillmoor.example"),
                    _real_mate(MATE, "kit@quillmoor.example"), _real_org(OWN, "Quillmoor Labs"))
    organisation_members(rows, OWNER)
    assert _by(rows)[OWN]["people"] == [MATE]
