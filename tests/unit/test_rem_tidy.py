"""Tidying a notebook an older version made (#1999, #2008): shaped on the owner's copy."""

from connectonion.rem.config import prepare
from connectonion.rem.files import Notebook, read_json, state_path, write_json
from connectonion.rem.tidy import tidy


def _person(notebook, record, name, address, investigated=False):
    notebook.stub_person(record, name, [address], email=address)
    if investigated:
        page = notebook.read(record).replace("not investigated yet", "investigated 2026-09-28")
        notebook.write(record, page)


def _state(root, **state):
    write_json(state_path(root, "map.json"), state)


def test_services_an_older_map_made_people_are_archived_and_investigated_pages_stay(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    _person(notebook, "people/apple.md", "Apple", "appleid@id.apple.com")                 # no row: its title is its domain
    _person(notebook, "people/github.md", "unsub+abc@reply.github.com", "unsub+abc@reply.github.com")
    _person(notebook, "people/clarity.md", "Microsoft Clarity", "maccount@microsoft.com")
    _person(notebook, "people/x.md", "X", "notify@x.com", investigated=True)             # someone's work: stays
    _person(notebook, "people/mia.md", "Mia Tan", "mia@acme.example")
    _state(tmp_path, people=[
        {"record": "people/clarity.md", "address": "maccount@microsoft.com", "name": "Microsoft Clarity",
         "sent": 0, "received": 1, "one_way": True},
        {"record": "people/mia.md", "address": "mia@acme.example", "name": "Mia Tan", "sent": 0, "received": 5,
         "one_way": True}])

    done = tidy(tmp_path)

    assert done["archived service"] == ["people/apple.md", "people/clarity.md", "people/github.md"]
    assert sorted(notebook.list("people")) == ["people/mia.md", "people/x.md"]
    assert (tmp_path / ".state/archived/people/apple.md").is_file()          # moved, never deleted
    log = read_json(state_path(tmp_path, "tidy.json"), [])
    assert {entry["page"] for entry in log} == set(done["archived service"])
    assert tidy(tmp_path) == {}                                             # idempotent: nothing left to do
    assert len(read_json(state_path(tmp_path, "tidy.json"), [])) == len(log)


def test_a_link_to_an_archived_page_keeps_its_name_and_loses_the_dead_link(tmp_path):
    """#2054: orgs/airbnb kept `[Airbnb](../people/airbnb-….md)` after tidy archived
    the service page; the reader showed the name and the click went nowhere."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    _person(notebook, "people/apple.md", "Apple", "appleid@id.apple.com")
    _person(notebook, "people/mia.md", "Mia Tan", "mia@acme.example")
    notebook.stub_org("orgs/apple.md", "Apple", ["apple.com"])
    org = notebook.read("orgs/apple.md")
    notebook.write("orgs/apple.md", org + "\n- [Apple Support](../people/apple.md); [Mia Tan](../people/mia.md)\n")

    done = tidy(tmp_path)

    assert "people/apple.md" in done["archived service"]
    text = notebook.read("orgs/apple.md")
    assert "- Apple Support; [Mia Tan](../people/mia.md)" in text      # the live link stays
    assert done["unlinked archived page"] == ["orgs/apple.md"]
    assert tidy(tmp_path) == {}


def test_the_owners_own_addresses_fold_into_their_page_and_real_people_never_do(tmp_path):
    """The owner's run offered sixteen addresses to --mine; four were friends who
    answer on other channels. Only addresses carrying the owner's words fold."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/aaron-xie.md", "Aaron Xie", ["openonionai@gmail.com"], email="openonionai@gmail.com")
    _person(notebook, "people/cx.md", "常兴", "aaronplus1996@gmail.com")
    _person(notebook, "people/confirmed.md", "xietianle@outlook.com", "xietianle@outlook.com")
    _person(notebook, "people/larry.md", "Larry", "larryleework7@gmail.com")
    _person(notebook, "people/aaron-smith.md", "Aaron Smith", "aaron.smith@firm.example")
    rows = [{"record": "people/cx.md", "address": "aaronplus1996@gmail.com", "name": "常兴", "sent": 108, "received": 0},
            {"record": "people/larry.md", "address": "larryleework7@gmail.com", "name": "Larry", "sent": 17,
             "received": 0},
            {"record": "people/aaron-smith.md", "address": "aaron.smith@firm.example", "name": "Aaron Smith",
             "sent": 9, "received": 3}]                                     # he replies: someone else
    asked = [{"address": row["address"], "sent": row["sent"], "record": row["record"]} for row in rows[:2]]
    _state(tmp_path, owner={"record": "people/aaron-xie.md",
                            "addresses": ["openonionai@gmail.com", "xietianle@outlook.com"]},
           people=[{"record": "people/aaron-xie.md", "classification": "account owner"}, *rows],
           possible_own_addresses=asked)

    done = tidy(tmp_path)

    assert done["folded into the owner's page"] == ["people/confirmed.md", "people/cx.md"]
    assert sorted(notebook.list("people")) == ["people/aaron-smith.md", "people/aaron-xie.md", "people/larry.md"]
    page = notebook.read("people/aaron-xie.md")
    assert "- Email: openonionai@gmail.com, xietianle@outlook.com [1], aaronplus1996@gmail.com [2]" in page
    assert "classification unassessed" not in page                          # not a correspondent of their own
    state = read_json(state_path(tmp_path, "map.json"), {})
    assert "aaronplus1996@gmail.com" in state["owner"]["addresses"]
    assert state["possible_own_addresses"] == []                            # Larry is not offered to --mine
    aliases = read_json(state_path(tmp_path, "aliases.json"), {})
    assert aliases["people/cx.md"]["into"] == "people/aaron-xie.md"


def test_a_skill_named_by_its_folder_folds_into_the_named_skill(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_skill("skills/catalog/nonfiction-refine.md", "nonfiction-refine", "/a/nonfiction-refine/SKILL.md",
                        "非虚构写作优化流程·编排器")
    notebook.stub_skill("skills/catalog/changxing-nonfiction-refine.md", "changxing-nonfiction-refine",
                        "/b/changxing-nonfiction-refine/SKILL.md", "非虚构写作优化流程·编排器")
    notebook.stub_skill("skills/catalog/linkedin-post.md", "linkedin-post", "/c/linkedin-post/SKILL.md", "Posts")
    notebook.stub_skill("skills/catalog/post.md", "post", "/c/post/SKILL.md", "Another skill")

    done = tidy(tmp_path)

    assert done == {"folded duplicate skill": ["skills/catalog/changxing-nonfiction-refine.md"]}
    assert "skills/catalog/linkedin-post.md" in notebook.list("skills")      # a shared suffix is not a copy


def test_old_coverage_lines_go_line_by_line_and_the_rest_stays(tmp_path):
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    page = ("# Finn\n\n## Contact\n- Handles: finn@town.com [2]\n- Also known as: Finn [1][2]\n\n"
            "## Uncertainties\n- Phone: none in the supplied mail. [2]\n- web: not searched; Wiki runs are offline\n\n"
            "## Sources\n- [1] gmail:abc — a mail\n- [2] investigation:coverage — observed 2026-09-28; high confidence\n\n"
            "Investigation: investigated 2026-09-28\n")
    notebook.write("people/finn.md", page)
    kept = ("# Atlas\n\n## Uncertainties\n- No related Codex messages were found. [1]\n\n## Sources\n"
            "- [1] investigation:coverage — source-collection record for this investigation.\n")
    notebook.write("projects/atlas.md", kept)

    done = tidy(tmp_path)

    assert done == {"removed line": ["people/finn.md"]}
    assert notebook.read("people/finn.md") == (
        "# Finn\n\n## Contact\n- Handles: finn@town.com\n- Also known as: Finn [1]\n\n"
        "## Uncertainties\n- Phone: none in the supplied mail.\n\n"
        "## Sources\n- [1] gmail:abc — a mail\n\nInvestigation: investigated 2026-09-28\n")
    assert notebook.read("projects/atlas.md") == kept                      # the runner's own notice is a fact it cites
    lines = [entry["line"] for entry in read_json(state_path(tmp_path, "tidy.json"), [])]
    assert "- web: not searched; Wiki runs are offline" in lines          # what went is on record


def test_a_notebook_without_state_is_left_alone(tmp_path):
    assert tidy(tmp_path / "missing") == {}


def test_an_address_confirmed_once_stays_the_owners_at_the_next_map(tmp_path, monkeypatch):
    from connectonion.rem.map import build_map
    prepare(tmp_path)
    (tmp_path / "installed").mkdir()
    row = {"name": "", "address": "aaronplus1996@gmail.com", "mails": 106, "sent": 106, "received": 0, "one_way": True}

    def mail_rows(clients, days, mine, coverage, errors=None, progress=None, **kw):
        own = {address.lower() for address in mine}
        return ([dict(row)] if row["address"] not in own else []), own

    monkeypatch.setattr("connectonion.rem.map._mail_rows", mail_rows)
    monkeypatch.setattr("connectonion.rem.map.scan_projects", lambda *a: [])
    build_map(tmp_path, {}, {}, skill_directories=[tmp_path / "installed"], mine=["aaronplus1996@gmail.com"])
    again = build_map(tmp_path, {}, {}, skill_directories=[tmp_path / "installed"])   # no --mine this time
    assert "aaronplus1996@gmail.com" in again["owner"]["addresses"]
    assert again["possible_own_addresses"] == []


# ------------------------------------------- the 1.9.0a5 acceptance run (#2017, #2018)


def test_the_owners_possibly_yours_lines_follow_what_is_still_asked(tmp_path):
    """#2017: the owner's page carried nine "Possibly also the owner's" lines, the
    same three addresses at different counts, two already confirmed and folded."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/aaron.md", "Aaron Xie", ["openonionai@gmail.com"], email="openonionai@gmail.com")
    asked = ["aaronplus1996@gmail.com (108 sent", "aaron@openonion.ai (22 sent", "aaronplus1996@gmail.com (101 sent",
             "aaron@openonion.ai (10 sent", "aaronchen@openonion.ai (10 sent", "aaronchen@openonion.ai (8 sent"]
    lines = "".join(f"- Possibly also the owner's: {one}, none received). If it is yours: co rem init --mine x\n"
                    for one in asked)
    page = notebook.read("people/aaron.md").replace("## Uncertainties\n", "## Uncertainties\n" + lines)
    notebook.write("people/aaron.md", page.replace("- Unknown — not investigated yet\n\n## Sources", "\n## Sources"))
    _person(notebook, "people/cx.md", "常兴", "aaronplus1996@gmail.com")
    _state(tmp_path, owner={"record": "people/aaron.md", "addresses": ["openonionai@gmail.com", "aaron@openonion.ai"]},
           people=[{"record": "people/cx.md", "address": "aaronplus1996@gmail.com", "name": "常兴", "sent": 108,
                    "received": 0}],
           possible_own_addresses=[{"address": "aaronchen@openonion.ai", "sent": 10, "record": "people/ac.md"}])

    tidy(tmp_path)

    page = notebook.read("people/aaron.md")
    kept = [line for line in page.splitlines() if line.startswith("- Possibly also the owner's:")]
    assert kept == ["- Possibly also the owner's: aaronchen@openonion.ai (10 sent, none received). "
                    "If it is yours: co rem init --mine x"]                   # confirmed ones gone, one line each
    assert "- Email: openonionai@gmail.com, aaronplus1996@gmail.com" in page
    assert tidy(tmp_path) == {} and notebook.read("people/aaron.md") == page  # idempotent


def test_organisation_pages_for_mailbox_providers_and_relays_are_archived(tmp_path):
    """#2018: orgs/yahoo-com-hk and orgs/luma-mail-com (253 mails, one sender) on the copy."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    for domain in ("yahoo.com.hk", "luma-mail.com", "hotmail.co.uk", "unsw.edu.au"):
        notebook.stub_org(f"orgs/{domain}.md", domain, [domain], [])
    notebook.stub_org("orgs/qq.md", "qq.com", ["qq.com"], [])
    notebook.write("orgs/qq.md", notebook.read("orgs/qq.md").replace("not investigated yet", "investigated 2026-09-28"))
    _state(tmp_path)

    done = tidy(tmp_path)

    assert done == {"archived organisation": ["orgs/hotmail.co.uk.md", "orgs/luma-mail.com.md",
                                              "orgs/yahoo.com.hk.md"]}
    assert sorted(notebook.list("orgs")) == ["orgs/qq.md", "orgs/unsw.edu.au.md"]   # investigated stays
    assert (tmp_path / ".state/archived/orgs/yahoo.com.hk.md").is_file()


# ------------------------------------------- the 1.9.0a6 acceptance run (#2028, #2031)


def test_a_folded_address_carries_its_evidence_and_the_uncertainty_it_resolved_goes(tmp_path):
    """#2028: `xietianle@outlook.com [1], aaron@openonion.ai, aaronplus1996@gmail.com` -- the
    folded two uncited -- and Uncertainties still calling them unresolved."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.write("people/aaron-xie.md", (
        "# Aaron Xie\n\n## Contact\n- Email: openonionai@gmail.com, xietianle@outlook.com [1]\n"
        "- Handles: Unknown\n\n## Uncertainties\n"
        "- Whether aaronplus1996@gmail.com and aaron@openonion.ai are his remains unresolved. [1]\n"
        "- Whether aaronchen@openonion.ai is his remains unresolved. [1]\n- Role: not in the mail. [1]\n\n"
        "## Sources\n- [1] gmail:abc — a mail\n\nInvestigation: investigated 2026-09-30\n"))
    _person(notebook, "people/cx.md", "常兴", "aaronplus1996@gmail.com")
    _person(notebook, "people/oo.md", "aaron@openonion.ai", "aaron@openonion.ai")
    _state(tmp_path, owner={"record": "people/aaron-xie.md",
                            "addresses": ["openonionai@gmail.com", "xietianle@outlook.com", "aaron@openonion.ai"]},
           people=[{"record": "people/cx.md", "address": "aaronplus1996@gmail.com", "name": "常兴", "sent": 108,
                    "received": 0}])

    tidy(tmp_path)

    page = notebook.read("people/aaron-xie.md")
    email = next(line for line in page.split("\n") if line.startswith("- Email: "))
    assert email == ("- Email: openonionai@gmail.com, xietianle@outlook.com [1], aaronplus1996@gmail.com [2], "
                     "aaron@openonion.ai [3]")
    sources = page.split("## Sources\n", 1)[1]
    assert "- [2] .state/map.json — 108 sent, none received, carrying the owner's name" in sources
    assert "- [3] .state/map.json — confirmed as the owner's own address" in sources
    assert "aaronplus1996@gmail.com and aaron@openonion.ai are his" not in page        # resolved: gone
    assert "- Whether aaronchen@openonion.ai is his remains unresolved. [1]" in page   # still open: kept
    assert "- Role: not in the mail. [1]" in page
    lines = [entry.get("line", "") for entry in read_json(state_path(tmp_path, "tidy.json"), [])]
    assert any("aaronplus1996@gmail.com and aaron@openonion.ai" in line for line in lines)
    assert tidy(tmp_path) == {}                                                   # idempotent
    assert notebook.read("people/aaron-xie.md") == page
