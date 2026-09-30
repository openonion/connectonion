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
    assert "- Email: openonionai@gmail.com, xietianle@outlook.com, aaronplus1996@gmail.com" in page
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

    def mail_rows(clients, days, mine, coverage, errors=None, progress=None):
        own = {address.lower() for address in mine}
        return ([dict(row)] if row["address"] not in own else []), own

    monkeypatch.setattr("connectonion.rem.map._mail_rows", mail_rows)
    monkeypatch.setattr("connectonion.rem.map.scan_projects", lambda *a: [])
    build_map(tmp_path, {}, {}, skill_directories=[tmp_path / "installed"], mine=["aaronplus1996@gmail.com"])
    again = build_map(tmp_path, {}, {}, skill_directories=[tmp_path / "installed"])   # no --mine this time
    assert "aaronplus1996@gmail.com" in again["owner"]["addresses"]
    assert again["possible_own_addresses"] == []
