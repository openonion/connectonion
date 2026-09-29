"""Where a maintenance batch should start, found without a model."""

from connectonion.wiki.config import prepare
from connectonion.wiki.files import Notebook
from connectonion.wiki.leads import page_leads


def test_the_deepest_project_and_the_people_named_are_the_leads(tmp_path):
    """A real pass ran `rg` over 1,187 pages for six turns to find these, then timed out."""
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_project("projects/home.md", "home", ["/Users/x"])
    notebook.stub_project("projects/connectonion.md", "connectonion", ["/Users/x/projects/connectonion"])
    notebook.stub_project("projects/other.md", "other", ["/Users/x/projects/other"])
    notebook.stub_person("people/dora.md", "Dora Chen", ["Dora"], email="dora@example.org")
    notebook.stub_person("people/ody.md", "Ody Zhou", ["欧弟"], email="ody@example.org")
    notebook.stub_person("people/al.md", "Al", [], email="al@example.org")
    items = [{"role": "extract", "project": "/Users/x/projects/connectonion/docs",
              "text": "Dora asked for the CRM export; 欧弟 reviewed it. Also: always test."}]
    leads = page_leads(notebook, items)
    assert leads[0] == "projects/connectonion.md"                 # the deepest, not the home directory
    assert "projects/home.md" not in leads and "projects/other.md" not in leads
    assert {"people/dora.md", "people/ody.md"} <= set(leads)       # by title word and by alias
    assert "people/al.md" not in leads                              # "Al" inside "always" is not Al


def test_the_owner_is_not_a_lead_and_projects_are_found_by_name(tmp_path):
    """Every session is the owner's own, so the owner's name is in all of it; a
    real batch about One and ConnectOnion was pointed at the owner's other address."""
    from connectonion.wiki.files import state_path, write_json
    prepare(tmp_path)
    notebook = Notebook(tmp_path)
    notebook.stub_person("people/me.md", "Aaron Xie", ["Aaron"], email="me@example.org")
    notebook.stub_person("people/me-too.md", "Aaron", [], email="me@other.example")
    notebook.stub_project("projects/one.md", "One", ["/w/one"])
    notebook.stub_project("projects/connectonion.md", "ConnectOnion", ["/w/co"])
    write_json(state_path(tmp_path, "map.json"), {"owner": {"record": "people/me.md"},
                                                  "possible_own_addresses": [{"record": "people/me-too.md"}]})
    items = [{"role": "extract", "text": "Aaron wants the One bot in Lark; ConnectOnion needs a release. one more."}]
    leads = page_leads(notebook, items)
    assert set(leads) == {"projects/one.md", "projects/connectonion.md"}


def test_the_home_directory_is_never_a_lead(tmp_path, monkeypatch):
    """A project page for /Users/<name> held every session that ran anywhere no
    other project covered, and its title is in every path: on the owner's
    notebook it was picked three nights running and filled with unrelated notes."""
    from pathlib import Path
    from connectonion.wiki.files import Notebook
    from connectonion.wiki.leads import page_leads
    home = Path.home()
    notebook = Notebook(tmp_path)
    notebook.stub_project("projects/home.md", home.name, [str(home)], sessions=2)
    notebook.stub_project("projects/tallyho.md", "tallyho", [str(home / "code" / "tallyho")], sessions=4)
    items = [{"project": str(home / "Documents" / "scratch"), "text": f"worked in {home}/Documents/scratch"},
             {"project": str(home / "code" / "tallyho"), "text": "ran the tests"}]
    leads = page_leads(notebook, items)
    assert "projects/home.md" not in leads
    assert "projects/tallyho.md" in leads


def test_the_map_does_not_make_the_home_directory_a_project():
    from pathlib import Path
    from connectonion.wiki.scan import project_exclusion
    assert project_exclusion(Path.home()) == "home directory"
    assert project_exclusion(Path.home().parent) == "home directory"
    assert project_exclusion(Path.home() / "code" / "tallyho") != "home directory"
